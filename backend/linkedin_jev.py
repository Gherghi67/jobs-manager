"""LinkedIn's runner: jev_runner drives the search, then this reads the listed jobs through the JSON
endpoint LinkedIn's own job page uses. Runs in jev-ultrafast's virtualenv; see jev_runner.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_runner  # noqa: E402
import linkedin  # noqa: E402

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


if __name__ == '__main__':
    jev_runner.main(linkedin, read_jobs)
