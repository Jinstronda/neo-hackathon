---
name: nday-pwn
description: Fingerprint the exact software versions a target runs, match them to recently disclosed vulnerabilities (zero-days-turned-n-days) that already have public exploits, and attack via the best match. Use to hack a target via known/fresh CVEs, find exploits for detected versions, do version-to-exploit matching or n-day exploitation, or weaponize a new disclosure. Covers deep version fingerprinting, CPE construction, CVE matching, KEV/EPSS prioritization, PoC location, adaptation, and verified exploitation. For real-target intrusion, run inside the breachbench kill chain.
---

# n-day pwn: version -> fresh CVE -> public exploit -> pwn

A "zero-day" is unknown to the vendor. The moment it is disclosed (advisory +
patch + PoC) it becomes an **n-day**, and for everyone who hasn't patched yet,
it still works like a zero-day. This technique skips original vulnerability
research entirely:

1. Fingerprint what exact software + version the target runs.
2. Match it against recently disclosed CVEs that already have public working
   exploits.
3. Strike during the patch gap (companies take 88-208 days on average to patch;
   ~32% of exploits appear on or before the CVE publication date; public PoCs
   typically appear within 1-7 days of disclosure).

Always operate within authorization (see breachbench for the full kill chain and
evidence rules).

## Stage 1, Fingerprint exact versions

Run black-box, escalating from passive to active. Record every finding as
`{product, exact_version, evidence, cpe}`.

**Active service fingerprinting:**
```bash
nmap -sV --version-intensity 5 -p- <target> -oA target
# If nmap returns a range (e.g. "Samba 3.X - 4.X"), pin the exact version with
# protocol-native tools: smbclient, ssh -v, ftp, smtp VRFY, HTTP OPTIONS, etc.
```

**Web stack fingerprinting:**
```bash
whatweb -a 3 <url> --log-json=whatweb.json      # aggressive, granular versions
httpx -u <url> -tech-detect                      # Wappalyzer engine, fast
curl -sI <url> | grep -iE "server|x-powered-by|x-generator|x-aspnet-version|via|x-served-by|x-amz"
wafw00f <url>                                    # WAF present? scan origin separately if possible
```

**Where versions hide (check all):**
- Headers: `Server`, `X-Powered-By`, `X-Generator`, custom `X-*` headers.
- HTML: `meta generator`, script paths with versions (`jquery-1.12.4.min.js`),
  HTML comments, JS globals, sourcemaps.
- Version files: `/CHANGELOG.md`, `/README`, `/package.json`, `/composer.json`,
  `/readme.html`, `/feed` (generator tag).
- Default error pages: trigger 404/403/500, default templates reveal Tomcat,
  Spring Boot, Nginx, IIS, etc.
- Product-specific endpoints: `/wp-json/`, `/administrator/`, `/login`,
  `/api/v1`, `/jira`, `/jenkins`.
- Client-side JS bundles: library versions inside comments/paths.

**Favicon hashing (works even on hardened sites, and pivots):**
```bash
python3 -c "
import mmh3, requests, base64
r = requests.get('<url>/favicon.ico', timeout=10)
print(mmh3.hash(base64.encodebytes(r.content)))"
# Then search Shodan for the hash to identify the product AND find
# other instances / origin IPs behind CDNs:  http.favicon.hash:<hash>
```

**Passive/historical (no packets to target):** Shodan, Censys, ZoomEye, FOFA,
SecurityTrails, Wayback Machine, historical banners often reveal versions even
if the live site is hardened today.

## Stage 2, Version -> CVE matching

1. Build the CPE 2.3 string: `cpe:2.3:a:vendor:product:version:*:*:*:*:*:*:*`.
2. Correlate across databases:
```bash
# Best one-shot: correlates NVD + GHSA + Exploit-DB + PoC-in-GitHub + Metasploit + nuclei
search_vulns -q "Apache HTTP Server 2.4.49"
search_vulns -q "cpe:2.3:a:apache:http_server:2.4.49:*:*:*:*:*:*:*" -f json

# NVD API
curl -s "https://services.nvd.nist.gov/rest/json/cves/2.0?cpeName=<cpe>"
```
3. Auto-match service scans: `searchsploit --nmap target.xml -v` and
   `nmap --script vulners`.
4. Active CVE testing: `nuclei -u <url> -tags cve`; a year's CVEs:
   `-t http/cves/2026/`; automatic: `nuclei -u <url> -as`.

Freshness matters: for unpatched odds, prioritize CVEs published in the last ~90
days, then KEV items of any age.

## Stage 3, Prioritize (KEV > EPSS > CVSS)

1. **CISA KEV**, confirmed exploited in the wild, authoritative:
```bash
curl -s https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json | jq '.vulnerabilities[].cveID'
```
2. **VulnCheck KEV** (broader) and nuclei tag: `nuclei -tags kev,vkev`.
3. **EPSS**, daily probability of exploitation in the next 30 days; >0.5 or
   percentile >90 is hot:
```bash
curl -s "https://api.first.org/data/v1/epss?cve=CVE-2026-XXXX" | jq '.data[0]'
```
4. **CVSS >= 7** *with* a public weaponized exploit, CVSS alone is only a lead,
   never a finding.

## Stage 4, Find working exploit code

If the CVE is fresher than the tooling below (under ~2 weeks, or not yet in
Exploit-DB / nuclei), run `cve-intake` first: it pulls new disclosures with
attested public exploits and filters them against the version you just
fingerprinted. Prove any PoC locally before letting it near the target.

Ranked by quality, prefer weaponized over raw PoCs:
```bash
searchsploit --cve 2026-XXXX            # local Exploit-DB; .rb = Metasploit-ready
searchsploit -m 7618                    # mirror exploit into cwd for reading/adapting
curl -s "https://poc-in-github.motikan2010.net/api/v1/?cve_id=CVE-2026-XXXX" | jq '.pocs[]'
gh search repos "CVE-2026-XXXX" --sort stars
msfconsole -q -x "search cve:CVE-2026-XXXX; exit"
nuclei -u <url> -id CVE-2026-XXXX
```

Also check researcher writeups (watchTowr, Project Zero), they often contain
full exploit chains. **If no public PoC exists yet**, the patch diff is a roadmap
(patch diffing with BinDiff/Diaphora/Ghidriff for closed source), and an LLM
agent can turn a patch into a working PoC within hours.

## Stage 5, Verify and adapt

- Confirm the fingerprinted version is *inside* the CVE's affected range
  (searchsploit fuzzy ranges lie, check NVD CPE constraints).
- **Backports**: Debian/Ubuntu/RHEL ship patched code under old version strings —
  check the distro security tracker before trusting a Linux-version match.
- PoCs are usually written against a different minor version, read the code,
  test against a local instance, adapt. For anything fresh or unattributed,
  local repro is mandatory: vulnerable build fires, patched build does not, in a
  throwaway container (`cve-intake` stage 3).
- Verify safely first (nuclei / version banner) before firing RCE.
- Exploit within authorized scope; document chain of evidence (breachbench rules).

## Report format

For each exploited CVE state: product + exact version + fingerprint evidence, CVE
ID, why it ranked (KEV/EPSS/CVSS), exploit source and quality, version-in-range
proof, and impact. Underclaim: a version match without exploitation is a lead,
not a finding.

**Adversary review (mandatory, always runs):** before writing this section, run
`adversary-review` on every finding and severity claim, grade demonstrated
impact (what exploitation actually yielded), not the CVE's theoretical CVSS; an
n-day on a system holding no private data caps at medium. No severity grade
leaves the mission without its verdict.

Key sources: nvd.nist.gov · api.first.org/data/v1/epss ·
cisa.gov/known-exploited-vulnerabilities-catalog · github.com/nomi-sec/PoC-in-GitHub ·
github.com/trickest/cve · exploit-db.com · github.com/projectdiscovery/nuclei-templates ·
search-vulns.com · sploitus.com · osv.dev
