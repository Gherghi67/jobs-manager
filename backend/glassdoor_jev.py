"""Glassdoor's runner: jev_runner drives the search, then this reads each listed job's schema.org JobPosting
from its Glassdoor page, fetched inside the signed-in tab. Runs in jev-ultrafast's virtualenv; see jev_runner.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glassdoor  # noqa: E402
import jev_runner  # noqa: E402

READ_JOBS = r"""(async ({limit}) => {
  const cards = [...document.querySelectorAll('[data-test="jobListing"][data-jobid]')]
    .filter(li => /^\d{5,20}$/.test(li.getAttribute('data-jobid'))).slice(0, limit);
  const text = html => {
    const marked = String(html || '').replace(/<br\s*\/?>|<\/(?:p|li|h\d|div|ul|ol)>/gi, '$&\n');
    return (new DOMParser().parseFromString(marked, 'text/html').body.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
  };
  const jobs = [];
  let failed = 0, limited = false;
  for (const li of cards) {
    const link = li.querySelector('a[data-test="job-title"]');
    const job = {id: li.getAttribute('data-jobid'), url: link?.href || '', title: link?.innerText.trim() || '',
      company: li.querySelector('[class*="EmployerProfile_compactEmployerName"]')?.innerText.trim() || '',
      location: li.querySelector('[data-test="emp-location"]')?.innerText.trim() || '',
      salary: li.querySelector('[data-test="detailSalary"]')?.innerText.trim() || ''};
    let posting = null;
    if (!limited && link && new URL(link.href).origin === location.origin) {
      try {
        const response = await fetch(link.href, {credentials: 'include'});
        if (response.status === 403 || response.status === 429) limited = true;
        else if (response.ok) {
          const page = new DOMParser().parseFromString(await response.text(), 'text/html');
          for (const script of page.querySelectorAll('script[type="application/ld+json"]')) {
            try {
              const data = JSON.parse(script.textContent);
              if (data && data['@type'] === 'JobPosting') posting = data;
            } catch (e) {}
          }
        }
      } catch (e) {}
      await new Promise(done => setTimeout(done, 300));
    }
    if (posting) {
      const address = posting.jobLocation?.address || (Array.isArray(posting.jobLocation) ? posting.jobLocation[0]?.address : null);
      const place = address ? [address.addressLocality, address.addressRegion, address.addressCountry?.name || address.addressCountry]
        .filter(x => typeof x === 'string' && x).join(', ') : '';
      Object.assign(job, {title: posting.title || job.title, company: posting.hiringOrganization?.name || job.company,
        location: place || job.location, workplace: posting.jobLocationType || null,
        countries: posting.applicantLocationRequirements || null, posted: posting.datePosted || '',
        employment: posting.employmentType || null, description: text(posting.description).slice(0, 20000)});
    } else failed++;
    // A job without its details still has the card's title, company and location.
    jobs.push(job);
  }
  return {cards: cards.length, jobs, failed, limited};
})"""


def read_jobs(cdp, session, limit):
    expression = f'{READ_JOBS}({json.dumps({"limit": limit})})'
    result = cdp('Runtime.evaluate', session_id=session, expression=expression, awaitPromise=True, returnByValue=True,
                 _response_timeout=90)
    found = result.get('result', {}).get('value')
    if result.get('exceptionDetails') or not isinstance(found, dict):
        raise glassdoor.GlassdoorError('The Glassdoor results page could not be read.')
    warnings = []
    if found['limited']:
        warnings.append(f'Glassdoor refused some detail reads; {found["failed"]} of {found["cards"]} roles have only their card.')
    elif found['failed']:
        warnings.append(f'{found["failed"]} Glassdoor job details could not be read; those roles have only their card.')
    return found['jobs'], warnings


if __name__ == '__main__':
    jev_runner.main(glassdoor, read_jobs)
