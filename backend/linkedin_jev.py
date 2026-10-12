"""Runs in jev-ultrafast's virtualenv, started by linkedin.fetch with jev-ultrafast as the working directory.

The Jev agent types the LinkedIn Jobs search in an owned tab of the Chrome profile signed in to
LinkedIn. Code checks each chosen action before it executes, then reads the listed jobs through
the JSON endpoint LinkedIn's own job page uses. Reads the request on stdin; prints one JSON line.
"""
import contextlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import linkedin  # noqa: E402

START = 'https://www.linkedin.com/jobs/search/'
MAX_ACTIONS = 16
MAX_DECISIONS = 40
# Consecutive stale executions of one target before pressing Escape, and before giving up.
STALE_ESCAPE, STALE_STOP = 2, 4
# Leaves linkedin.TIMEOUT room to close the tab and report.
BUDGET = 150
READ_JOBS = r"""(async ({limit}) => {
  const ids = [...new Set([...document.querySelectorAll('[data-occludable-job-id],[data-job-id]')]
    .map(e => e.getAttribute('data-occludable-job-id') || e.getAttribute('data-job-id'))
    .filter(id => /^\d{5,20}$/.test(id || '')))].slice(0, limit);
  const csrf = (document.cookie.match(/JSESSIONID="?([^";]+)/) || [])[1];
  if (!csrf) return {signed_in: false, ids: ids.length, jobs: [], failed: 0, limited: false};
  const cardCompany = id => document.querySelector(`[data-occludable-job-id="${id}"] .artdeco-entity-lockup__subtitle`)
    ?.innerText.trim() || '';
  const jobs = [];
  let failed = 0, limited = false;
  for (const id of ids) {
    let response;
    try {
      response = await fetch(`/voyager/api/jobs/jobPostings/${id}?decorationId=` +
        'com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-65',
        {headers: {'csrf-token': csrf, accept: 'application/vnd.linkedin.normalized+json+2.1'}});
    } catch (e) { failed++; continue; }
    if (response.status === 429) { limited = true; break; }
    const body = response.ok ? await response.json().catch(() => null) : null;
    const d = body?.data;
    if (!d) { failed++; continue; }
    if (d.jobState && d.jobState !== 'LISTED') continue;
    const ref = d.companyDetails?.['*companyResolutionResult'] || d.companyDetails?.company;
    const company = (body.included || []).find(x => ref && x.entityUrn === ref)?.name ||
      d.companyDetails?.companyName || cardCompany(id);
    const types = (d.workplaceTypes || []).map(u => Number(String(u).split(':').pop()));
    const workplace = [2, 3, 1].find(t => types.includes(t)) ?? (d.workRemoteAllowed ? 2 : null);
    jobs.push({id, title: d.title || '', company, location: d.formattedLocation || '', workplace,
      listed_at: d.listedAt || d.originalListedAt || 0, employment: d.formattedEmploymentStatus || '',
      description: (d.description?.text || '').slice(0, 20000)});
    await new Promise(done => setTimeout(done, 250));
  }
  return {signed_in: true, ids: ids.length, jobs, failed, limited};
})"""


def load_env(path):
    """jev-ultrafast's own .env, the way its inspector loads it: set only what isn't set."""
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


@contextlib.contextmanager
def attached(cdp, target):
    session = cdp('Target.attachToTarget', targetId=target['targetId'], flatten=True)['sessionId']
    try:
        yield session
    finally:
        with contextlib.suppress(Exception):
            cdp('Target.detachFromTarget', sessionId=session)


def signed_in(cdp, tab):
    with attached(cdp, tab) as session:
        cookies = cdp('Network.getCookies', session_id=session, urls=['https://www.linkedin.com/'])['cookies']
    # Only the cookie's presence is checked; its value is never read or kept.
    return any(c['name'] == 'li_at' for c in cookies)


def visible(cdp, tab):
    with attached(cdp, tab) as session:
        result = cdp('Runtime.evaluate', session_id=session, expression='document.visibilityState', returnByValue=True)
    return result.get('result', {}).get('value') == 'visible'


def open_tab(cdp):
    """Chrome's CDP creates tabs only in its default profile, so a tab of the profile signed in to
    LinkedIn opens the agent's tab, as a link would. Returns the new tab's target id."""
    profiles = {}
    for t in cdp('Target.getTargets')['targetInfos']:
        if t['type'] == 'page' and t['url'].startswith('https://'):
            profiles.setdefault(t.get('browserContextId'), []).append(t)
    tabs = None
    for candidates in profiles.values():
        with contextlib.suppress(Exception):
            if signed_in(cdp, candidates[0]):
                tabs = candidates
                break
    if not tabs:
        raise linkedin.LinkedInError('No open Chrome profile is signed in to LinkedIn. Open a window of that profile on the Mac.')
    # Open from the tab on screen, so Chrome returns to it when the agent's tab closes.
    opener = tabs[0]
    for tab in tabs[:20]:
        with contextlib.suppress(Exception):
            if visible(cdp, tab):
                opener = tab
                break
    before = {t['targetId'] for t in cdp('Target.getTargets')['targetInfos']}
    with attached(cdp, opener) as session:
        cdp('Runtime.evaluate', session_id=session, expression="void window.open('about:blank', '_blank', 'noopener')",
            userGesture=True)
    for _ in range(50):
        for t in cdp('Target.getTargets')['targetInfos']:
            if t['type'] == 'page' and t['targetId'] not in before and t.get('browserContextId') == opener.get('browserContextId'):
                return t['targetId']
        time.sleep(0.1)
    raise linkedin.LinkedInError('Chrome did not open a tab for the LinkedIn search.')


def profile_browser(base, cdp, ensure_daemon):
    """jev's Browser, with its tab in the signed-in profile instead of Chrome's default one."""
    class ProfileBrowser(base):
        def __init__(self, url):
            ensure_daemon()
            self.target = open_tab(cdp)
            try:
                self.session = cdp('Target.attachToTarget', targetId=self.target, flatten=True)['sessionId']
                # The rest matches Browser.__init__.
                self.call('Emulation.setDeviceMetricsOverride', width=1120, height=780, deviceScaleFactor=1, mobile=False)
                self.call('Emulation.setFocusEmulationEnabled', enabled=True)
                self.call('Page.navigate', url=url)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and self.evaluate('document.readyState') != 'complete':
                    time.sleep(0.02)
            except BaseException:
                self.close()
                raise
    return ProfileBrowser


def settle(browser, marker, deadline, still=1.0, cap=8.0):
    """Wait until jev's page marker stops changing. LinkedIn keeps rendering for seconds after each load,
    and a decision made meanwhile goes stale before it executes, costing another model request."""
    end = min(time.monotonic() + cap, deadline)
    last, since = None, time.monotonic()
    while time.monotonic() < end:
        try:
            current = browser.evaluate(marker)
        except Exception:  # noqa: BLE001 - a navigating page is a changing page
            current = None
        now = time.monotonic()
        if current is None or current != last:
            last, since = current, now
        elif now - since >= still:
            return
        time.sleep(0.25)


def drive(agent, stale, deadline, log, wait=lambda: None):
    """Agent.run's tick, with a code check between the decision and its execution.
    Calls wait before each decision, appends each decision's label to log, and returns
    the number of executed actions."""
    state, repeats, last = agent.state, 0, None
    while state['status'] not in ('done', 'blocked'):
        if time.monotonic() > deadline:
            raise linkedin.LinkedInError('The LinkedIn search took too long; the browser agent stopped.')
        wait()
        # Each decision is one TypeSafe request, including those a page change makes stale.
        if len(state['decisions']) >= MAX_DECISIONS:
            raise linkedin.LinkedInError(f'The LinkedIn search needed more than {MAX_DECISIONS} agent decisions; stopped.')
        label = None
        try:
            agent.command('predict', {})
            choice = state['decision']['choice']
            action = next((a for a in state['page']['actions'] if a['id'] == choice), None)
            label = action['label'][:80] if action else choice
            log.append(label)
            if action:
                reason = linkedin.refused(action)
                if reason:
                    raise linkedin.LinkedInError(f'Stopped before the browser agent used {reason}; nothing was clicked.')
                if len(state['history']) >= MAX_ACTIONS:
                    raise linkedin.LinkedInError(f'The LinkedIn search needed more than {MAX_ACTIONS} browser actions; stopped.')
            agent.command('act', {'fingerprint': state['page']['fingerprint']})
            repeats, last = 0, None
        except stale:
            # jev hit-tests the target just before input and reports a covered one as stale,
            # but the model never learns that, so it keeps choosing the same target.
            repeats, last = (repeats + 1 if label is not None and label == last else 1), label
            if label is not None:
                log[-1] += ' (stale)'
            if repeats >= STALE_STOP:
                raise linkedin.LinkedInError(f'LinkedIn kept covering "{label[:60]}"; the browser agent stopped.')
            if repeats == STALE_ESCAPE:
                # Escape closes the menu or suggestion list that usually covers it.
                for kind in ('keyDown', 'keyUp'):
                    agent.browser.call('Input.dispatchKeyEvent', type=kind, key='Escape', code='Escape', windowsVirtualKeyCode=27)
                log.append('Escape (pressed by code)')
                time.sleep(0.2)
            state['decision'] = None
            state['status'] = 'ready'
            state['page'] = agent.browser.observe(screenshot=False)
        if not linkedin.on_jobs(state['page']['url']):
            raise linkedin.LinkedInError('The browser agent left LinkedIn Jobs; stopped.')
    if state['status'] != 'done':
        raise linkedin.LinkedInError('The browser agent could not complete the LinkedIn search.')
    return len(state['history'])


def read_jobs(cdp, session, limit):
    expression = f'{READ_JOBS}({json.dumps({"limit": limit})})'
    result = cdp('Runtime.evaluate', session_id=session, expression=expression, awaitPromise=True, returnByValue=True,
                 _response_timeout=90)
    found = result.get('result', {}).get('value')
    if result.get('exceptionDetails') or not isinstance(found, dict):
        raise linkedin.LinkedInError('The LinkedIn results page could not be read.')
    if not found['signed_in']:
        raise linkedin.LinkedInError('The Chrome profile is no longer signed in to LinkedIn.')
    warnings = []
    if found['limited']:
        warnings.append(f'LinkedIn slowed down detail reads; {len(found["jobs"])} of {found["ids"]} roles were read.')
    if found['failed']:
        warnings.append(f'{found["failed"]} LinkedIn job details could not be read.')
    return found['jobs'], warnings


def main():
    out, sys.stdout = sys.stdout, sys.stderr  # Library output must not corrupt the JSON line.
    started = time.monotonic()
    agent, decisions = None, []
    result = dict(status='error', message='The LinkedIn browser agent was interrupted.')
    try:
        req = json.loads(sys.stdin.read())
        load_env(Path.cwd() / '.env')
        from browser_harness.admin import ensure_daemon
        from browser_harness.helpers import cdp
        import jev_ultrafast.agent as jev_agent
        from jev_ultrafast.browser import MARKER, Browser, StalePage

        jev_agent.Browser = profile_browser(Browser, cdp, ensure_daemon)
        agent = jev_agent.Agent(START, req['goal'])
        deadline = started + BUDGET
        actions = drive(agent, StalePage, deadline, decisions, lambda: settle(agent.browser, MARKER, deadline))
        page = agent.state['page']
        fields = [a.get('value') or '' for a in page['actions'] if a['kind'] == 'fill']
        warnings = linkedin.check_results(page['url'], req, fields)
        jobs, more = read_jobs(cdp, agent.browser.session, req['limit'])
        result = dict(status='ok', jobs=jobs, warnings=warnings + more, actions=actions, url=page['url'],
                      decisions=len(agent.state['decisions']), elapsed_ms=round((time.monotonic() - started) * 1000))
    except linkedin.LinkedInError as exc:
        result = dict(status='error', message=str(exc))
    except KeyError as exc:
        result = dict(status='error', message=f'jev-ultrafast is missing the setting {exc}.')
    except (ValueError, RuntimeError, TimeoutError) as exc:
        # jev and browser-harness raise these with messages meant for people.
        result = dict(status='error', message=f'Browser agent: {exc}')
    except Exception as exc:  # noqa: BLE001
        result = dict(status='error', message=f'{type(exc).__name__}: the LinkedIn browser agent failed.')
    finally:
        if agent:
            # The service keeps this to show what LinkedIn searches cost.
            result['usage'] = linkedin.usage_of(agent.state)
            # For diagnosis from the command line; the service ignores it.
            result['decided'] = decisions
            result['trace'] = [f"{h['kind']} {h['action'][:80]}" + (f" = {h['text']!r}" if h['text'] else '') +
                               f" -> {urlparse(h['url'] or '').path}" for h in agent.state['history']]
            with contextlib.suppress(Exception):
                agent.close()
    out.write(json.dumps(result) + '\n')
    out.flush()


if __name__ == '__main__':
    main()
