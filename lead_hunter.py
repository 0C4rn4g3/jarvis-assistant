"""Lead Hunter Mode for Jarvis.
Scouts local businesses near the user, audits their website & client traction,
identifies conversion leaks (missing SSL, non-mobile friendly, no analytics, no social presence,
or zero website), filters for recent businesses (2020 forward), links Google Maps listings,
strictly excludes directories/aggregators (retaining ONLY businesses with their own website),
ranks them by lowest traction, and pushes cold outreach lead lists to the user."""

import json, os, re, time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import requests
from ddgs import DDGS
import store
import system

LEADS_FILE = os.path.join(store.DATA, "leads.json")
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

AGGREGATOR_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com",
    "twitter.com", "x.com", "pinterest.com", "reddit.com", "tripadvisor.com",
    "wikipedia.org", "yellowpages.com", "yelp.com", "google.com", "whatclinic.com",
    "starofservice.com", "starofservice.ro", "placedigger.com", "ro.placedigger.com",
    "findglocal.com", "yably.com", "yably.ro", "auto-repair.shop", "carmechanic.expert",
    "booking.dentist", "dentavacation.com", "paginiaurii.ro", "storia.ro", "olx.ro",
    "emag.ro", "publi24.ro", "lajumate.ro", "anuntul.ro", "bizoo.ro", "infobel.com",
    "topfirme.com", "listafirme.ro", "firme.ro", "totalfirme.ro", "romanian-companies.eu",
    "cylex.ro", "cylex-romania.ro", "la-stomatolog.ro", "dentalmap.ro", "med.ro",
    "doctorbun.ro", "sfatulmedicului.ro", "romaniaturistica.ro", "ghidul.ro", "ghidulb2b.ro",
    "firme-bihor.ro", "deschis.ro", "servicepedia.ro", "homerun.ro", "prinbucuresti.ro",
    "bucuresteni.ro", "topclinics.ro", "termene.ro", "topfirme.ro", "firme.info",
    "recomand.ro", "orasul.biz", "catalogfirme.ro", "portal-firme.ro", "catalog-firme.com",
    "afacerilacheie.ro", "cartierulmeu.ro", "ziaruldeafaceri.ro", "locanto.ro", "bing.com",
    "yandex.com", "yahoo.com", "duckduckgo.com", "nicelocal.ro", "near-place.com", "cylex.net.ro"
}

DIRECTORY_KEYWORDS = [
    "firme", "catalog", "directory", "pagini", "yellowpages", "ghid", "placedigger",
    "servicepedia", "deschis", "topclinics", "dentalmap", "doctorbun", "whatclinic",
    "starofservice", "cylex", "anunt", "portal", "yably", "afaceri", "repair.shop",
    "nicelocal", "near-place"
]


def is_own_website(url):
    """Verifies that a URL belongs to the actual business, NOT a directory, scraper, social media, or aggregator."""
    if not url or url.lower() in ("no website", "none", "n/a"):
        return False
    clean = url if "://" in url else "https://" + url
    try:
        parsed = urllib.parse.urlparse(clean)
        domain = parsed.netloc.lower().replace("www.", "")
        if not domain:
            return False
        if any(domain == agg or domain.endswith("." + agg) for agg in AGGREGATOR_DOMAINS):
            return False
        if any(k in domain for k in DIRECTORY_KEYWORDS):
            return False
        path = parsed.path.lower()
        if any(p in path for p in ["/category/", "/catalog/", "/firme/", "/places/", "/top-", "/ecat/", "/tag/"]):
            return False
        return True
    except Exception:
        return False


def get_saved_leads():
    """Retrieve the latest cached leads from disk."""
    if os.path.exists(LEADS_FILE):
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_leads(leads):
    """Save leads to disk."""
    try:
        os.makedirs(store.DATA, exist_ok=True)
        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[lead_hunter] Failed to save leads: {e}", flush=True)


def resolve_location(location=""):
    loc = (location or "").strip()
    if not loc or loc.lower() in ("near me", "here", "local", "my city", "current location"):
        city = store.settings().get("home_city", "").strip()
        if city:
            return city
        return "Bucharest"
    return loc


def clean_business_name(title, domain=""):
    parts = [p.strip() for p in re.split(r'\s*[-|–—:•]\s*', title) if p.strip()]
    name = ""
    for p in parts:
        p_clean = re.sub(r'^(?:Top\s*\d+|Cele mai bune\s*\d*|Best\s*\d*|Ghid|Ghidul|Cabinet|Clinica|Salon|Acasa|Home|Welcome)\s*', '', p, flags=re.I).strip()
        if p_clean and len(p_clean) >= 2 and p_clean.lower() not in ("acasa", "home", "welcome", "bucuresti", "romania", "index", "official", "pagina principala"):
            name = p_clean
            break
    if not name and parts:
        name = parts[0]
    if (not name or name.lower() in ("acasa", "home", "welcome", "bucuresti", "romania")) and domain:
        clean_domain = domain.split(".")[0].replace("-", " ").replace("_", " ").title()
        if len(clean_domain) >= 3:
            name = clean_domain
    return name or title[:30].strip()


def is_valid_business_name(name):
    name_lower = name.lower()
    generic_words = [
        "cele mai bune", "top 10", "top 5", "lista service", "lista firme",
        "automotive repair shop in", "dentists in bucharest", "dental clinics in",
        "cabinete stomatologice", "clinici stomatologice", "anunturi", "directory", "catalog"
    ]
    if any(g in name_lower for g in generic_words):
        return False
    if len(name.split()) > 7:
        return False
    return True


def find_businesses(niche="dental clinic", location="", limit=35):
    """Search for local businesses using multi-query DuckDuckGo search + OpenStreetMap Nominatim.
    Strictly filters out aggregators and directory scrapers."""
    loc = resolve_location(location)
    niche_clean = (niche or "business").strip()

    seen_domains = set()
    seen_names = set()
    candidates = []

    RO_NICHES = {
        "dental": [f"stomatologie {loc}", f"cabinet stomatologic {loc}", f"clinica stomatologica {loc}"],
        "dentist": [f"stomatologie {loc}", f"cabinet stomatologic {loc}", f"clinica stomatologica {loc}"],
        "auto": [f"service auto {loc}", f"mecanic auto {loc}", f"reparatii auto {loc}"],
        "repair": [f"service auto {loc}", f"reparatii {loc}"],
        "salon": [f"salon infrumusetare {loc}", f"barbershop {loc}", f"frizerie {loc}"],
        "barber": [f"barbershop {loc}", f"frizerie {loc}"],
        "gym": [f"sala fitness {loc}", f"sala forta {loc}"],
        "fitness": [f"sala fitness {loc}", f"antrenor personal {loc}"],
        "plumber": [f"instalator {loc}", f"instalatii sanitare {loc}"],
        "electrician": [f"electrician autorizat {loc}", f"instalatii electrice {loc}"],
        "lawyer": [f"avocat {loc}", f"cabinet avocat {loc}"],
        "real estate": [f"agentie imobiliara {loc}", f"imobiliare {loc}"],
        "vet": [f"cabinet veterinar {loc}", f"clinica veterinara {loc}"],
        "cleaning": [f"firma curatenie {loc}", f"servicii curatenie {loc}"],
        "accounting": [f"firma contabilitate {loc}", f"expert contabil {loc}"],
        "bakery": [f"brutarie {loc}", f"patiserie {loc}"]
    }

    # 1. Multi-query web search to discover dozens of real local businesses
    queries = [
        f"{niche_clean} {loc}",
        f"{niche_clean} {loc} contact",
        f"cabinet {niche_clean} {loc}",
        f"clinica {niche_clean} {loc}"
    ]
    for key, expanded_queries in RO_NICHES.items():
        if key in niche_clean.lower():
            queries.extend(expanded_queries)
            break

    with DDGS() as ddgs:
        for q in queries:
            try:
                for r in ddgs.text(q, max_results=15):
                    url = r.get("href", "")
                    if not is_own_website(url):
                        continue

                    domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
                    if not domain or domain in seen_domains:
                        continue
                    seen_domains.add(domain)

                    title = r.get("title", "")
                    raw_name = clean_business_name(title, domain)
                    norm_name = re.sub(r"[^\w\s]", "", raw_name.lower())
                    if not raw_name or norm_name in seen_names or len(raw_name) < 2:
                        continue
                    if not is_valid_business_name(raw_name):
                        continue
                    seen_names.add(norm_name)

                    maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(raw_name + ' ' + loc)}"
                    candidates.append({
                        "name": raw_name,
                        "url": url,
                        "phone": "N/A",
                        "address": loc,
                        "maps_url": maps_url,
                        "niche": niche_clean,
                        "location": loc
                    })
                    if len(candidates) >= limit:
                        break
            except Exception as e:
                print(f"[lead_hunter] Query '{q}' error: {e}", flush=True)
            if len(candidates) >= limit:
                break

    # 2. OpenStreetMap Nominatim for additional verified places
    if len(candidates) < limit:
        try:
            headers = {"User-Agent": "JarvisLeadHunter/1.0 (B2B Lead Intelligence)"}
            params = {
                "q": f"{niche_clean} in {loc}",
                "format": "json",
                "addressdetails": 1,
                "extratags": 1,
                "limit": 25
            }
            r = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=8)
            if r.ok:
                for item in r.json():
                    raw_name = item.get("display_name", "").split(",")[0].strip()
                    norm_name = re.sub(r"[^\w\s]", "", raw_name.lower())
                    if not raw_name or norm_name in seen_names or len(raw_name) < 2:
                        continue
                    if not is_valid_business_name(raw_name):
                        continue
                    seen_names.add(norm_name)

                    tags = item.get("extratags") or {}
                    raw_url = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""
                    url = raw_url.strip() if is_own_website(raw_url) else ""

                    if url:
                        domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
                        if domain in seen_domains:
                            continue
                        seen_domains.add(domain)

                    phone = tags.get("phone") or tags.get("contact:phone") or "N/A"
                    addr_dict = item.get("address") or {}
                    addr_parts = [addr_dict.get(k, "") for k in ("road", "suburb", "city", "county")]
                    clean_addr = ", ".join(p for p in addr_parts if p) or loc

                    lat = item.get("lat")
                    lon = item.get("lon")
                    if lat and lon:
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                    else:
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(raw_name + ' ' + loc)}"

                    candidates.append({
                        "name": raw_name,
                        "url": url,
                        "phone": phone.strip(),
                        "address": clean_addr,
                        "maps_url": maps_url,
                        "niche": niche_clean,
                        "location": loc
                    })
        except Exception as e:
            print(f"[lead_hunter] Nominatim search failed: {e}", flush=True)

    return candidates[:limit]


def audit_website(url):
    """Audit a website for client traction signals, conversion leaks, and mobile readiness.
    Enforces strict 2020+ recency verification and filters out directory aggregator pages."""
    res = {
        "url": url,
        "is_online": False,
        "ssl": False,
        "status_code": 0,
        "response_time_ms": 0,
        "mobile_viewport": False,
        "socials": [],
        "analytics": False,
        "copyright_year": None,
        "is_recent": True,
        "is_own_site": True,
        "issues": []
    }
    if not url or url == "No Website":
        res["issues"].append("Zero web presence (No website registered)")
        return res

    clean_url = url if url.startswith("http://") or url.startswith("https://") else f"https://{url}"

    # Verify domain is own website
    if not is_own_website(clean_url):
        res["is_own_site"] = False
        res["issues"].append("Directory / Aggregator page (not business's own website)")
        return res

    t0 = time.time()
    try:
        r = requests.get(clean_url, timeout=7, headers={"User-Agent": DEFAULT_UA}, verify=False)
        res["response_time_ms"] = int((time.time() - t0) * 1000)
        res["status_code"] = r.status_code
        res["is_online"] = (200 <= r.status_code < 400)
        res["ssl"] = r.url.startswith("https://")
        html = r.text

        # Verify page content is not a directory
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        if title_match:
            page_title = title_match.group(1).lower()
            if any(k in page_title for k in ("cele mai bune", "top 10", "catalog firme", "lista firme", "director firme", "servicepedia", "placedigger", "anunturi")):
                res["is_own_site"] = False
                res["issues"].append("Directory listing (not business's own website)")
                return res

        # 1. Viewport (Mobile responsiveness)
        if re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I):
            res["mobile_viewport"] = True
        else:
            res["issues"].append("No mobile viewport meta tag (fails on smartphones)")

        # 2. SSL
        if not res["ssl"]:
            res["issues"].append("Insecure HTTP only (no SSL certificate)")

        # 3. Response speed
        if res["response_time_ms"] > 2500:
            res["issues"].append(f"Slow response latency ({res['response_time_ms']}ms)")

        # 4. Social presence
        for soc in ("facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com"):
            if soc in html.lower():
                res["socials"].append(soc.split(".")[0].capitalize())
        if not res["socials"]:
            res["issues"].append("No social media channels linked")

        # 5. Tracking / Ads
        if any(x in html for x in ("googletagmanager", "google-analytics", "gtag", "fbq(", "analytics.js")):
            res["analytics"] = True
        else:
            res["issues"].append("No analytics / Meta Pixel (no ad traffic measurement)")

        # 6. Recency check (Copyright & footer years)
        cp_years = [int(y) for y in re.findall(r'(?:copyright|©|\(c\))\s*(?:[0-9]{4}\s*[-–/]\s*)?([12][0-9]{3})', html, re.I) if 1990 <= int(y) <= 2030]
        footer = html[-4000:]
        footer_years = [int(y) for y in re.findall(r'\b(20[0-9]{2})\b', footer) if 2000 <= int(y) <= 2030]
        all_years = cp_years + footer_years
        if all_years:
            latest = max(all_years)
            res["copyright_year"] = latest
            if latest < 2020:
                res["is_recent"] = False
                res["issues"].append(f"Outdated site from {latest} (prior to 2020)")
            elif latest < 2023:
                res["issues"].append(f"Older copyright notice (© {latest})")

    except requests.exceptions.SSLError:
        res["issues"].append("Broken/expired SSL certificate")
        res["is_online"] = False
    except requests.exceptions.Timeout:
        res["issues"].append("Website timed out (>7s load)")
        res["is_online"] = False
    except Exception as e:
        res["issues"].append(f"Site unreachable: {str(e)[:45]}")
        res["is_online"] = False

    return res


def calculate_traction_score(audit):
    """Calculates client traction score (0 to 100). Lower score = lowest traction / prime outreach opportunity."""
    if not audit.get("url") or audit.get("url") == "No Website":
        return 5, "Critical (No Website)"

    if not audit.get("is_online"):
        return 10, "Critical (Offline / Broken)"

    score = 75
    if not audit.get("mobile_viewport"):
        score -= 25
    if not audit.get("ssl"):
        score -= 20
    if not audit.get("analytics"):
        score -= 15
    if not audit.get("socials"):
        score -= 10
    if audit.get("response_time_ms", 0) > 2500:
        score -= 10
    if audit.get("copyright_year") and audit["copyright_year"] < 2023:
        score -= 15

    score = max(10, min(95, score))

    if score <= 30:
        level = "Critical Low Traction"
    elif score <= 50:
        level = "Low Traction"
    elif score <= 70:
        level = "Moderate Traction"
    else:
        level = "High Traction"

    return score, level


def build_pitch_angle(issues, name, niche):
    """Generates a tailored B2B cold pitch angle based on specific detected flaws."""
    if any("Zero web presence" in i for i in issues):
        return f"Pitch custom landing page + Google Maps GBP setup: {name} is losing local clients to competitors with active search rankings."
    if any("No mobile viewport" in i for i in issues):
        return f"Pitch responsive mobile overhaul: Site is broken for 60%+ of phone visitors searching for {niche}."
    if any("Insecure HTTP" in i for i in issues) or any("SSL" in i for i in issues):
        return f"Pitch security & SSL installation: Browsers flag {name} as 'Not Secure', scaring away customers."
    if any("Outdated copyright" in i for i in issues) or any("prior to 2020" in i for i in issues):
        return f"Pitch modern 2026 redesign: Visitors assume business may be closed due to neglected website."
    if any("No analytics" in i for i in issues):
        return f"Pitch digital growth & conversion funnel: No visitor tracking or retargeting currently in place."
    return f"Pitch SEO optimization and customer acquisition funnel."


def scan_leads(niche="dental clinic", location="", limit=15, send_phone=True, websites_only=False, **kwargs):
    """End-to-end scanner: discovers local businesses, audits their websites, filters for 2020+ recency,
    retains ONLY businesses with their own website (or no website), ranks lowest client traction first,
    saves the list, and beams it to paired mobile devices."""
    loc = resolve_location(location)
    candidates = find_businesses(niche, loc, limit=max(limit * 3, 30))

    if not candidates:
        return {"ok": False, "message": f"No businesses found for '{niche}' in {loc}."}

    results = []

    def process_candidate(b):
        url = b.get("url") or ""

        # If websites_only is requested and business has no website, skip
        if websites_only and (not url or url == "No Website"):
            return None

        # For businesses that have websites: ONLY add them if they have THEIR OWN WEBSITE
        if url and url != "No Website":
            if not is_own_website(url):
                return None

        audit = audit_website(url)

        # Reject if audit revealed it's an aggregator / directory listing
        if not audit.get("is_own_site", True):
            return None

        # Strict 2020+ recency filter: skip sites with detected copyright older than 2020
        if audit.get("is_recent") is False or (audit.get("copyright_year") and audit["copyright_year"] < 2020):
            return None

        score, level = calculate_traction_score(audit)
        issues = audit["issues"] or ["Basic template with low social engagement"]
        pitch = build_pitch_angle(issues, b["name"], niche)

        maps_url = b.get("maps_url") or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(b['name'] + ' ' + loc)}"

        return {
            "name": b["name"],
            "url": url or "No Website",
            "maps_url": maps_url,
            "phone": b.get("phone", "N/A") or "N/A",
            "address": b.get("address", loc) or loc,
            "niche": niche,
            "location": loc,
            "traction_score": score,
            "traction_level": level,
            "issues": issues,
            "pitch_angle": pitch,
            "ssl": audit.get("ssl", False),
            "mobile_viewport": audit.get("mobile_viewport", False),
            "response_time_ms": audit.get("response_time_ms", 0),
            "copyright_year": audit.get("copyright_year")
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        raw_results = list(pool.map(process_candidate, candidates))

    # Retain non-null items passing filters
    results = [r for r in raw_results if r is not None]

    # Sort ASCENDING: lowest client traction first (highest opportunity)
    results.sort(key=lambda x: (x["traction_score"], len(x["issues"]) * -1))
    top_leads = results[:limit]

    # Persist to disk
    save_leads(top_leads)

    # Format markdown report with Google Maps links
    report_lines = [
        f"🎯 **Lead Hunter Report: Lowest Client Traction in {loc}**",
        f"*Keyword:* `{niche}` · *Audited:* {len(results)} verified businesses · *Top Opportunities:* {len(top_leads)}\n"
    ]

    for idx, lead in enumerate(top_leads, start=1):
        score_badge = f"🔴 {lead['traction_score']}/100 ({lead['traction_level']})" if lead['traction_score'] <= 40 else f"🟡 {lead['traction_score']}/100 ({lead['traction_level']})"
        report_lines.append(f"**{idx}. {lead['name']}** — {score_badge}")
        report_lines.append(f"- 🌐 **Site**: {lead['url']}")
        report_lines.append(f"- 📍 **Google Maps**: [Open Location]({lead['maps_url']})")
        if lead['phone'] != "N/A":
            report_lines.append(f"- 📞 **Phone**: {lead['phone']}")
        report_lines.append(f"- ⚠️ **Leaks**: {', '.join(lead['issues'][:3])}")
        report_lines.append(f"- 💡 **Pitch**: {lead['pitch_angle']}\n")

    report_text = "\n".join(report_lines)

    # Send to paired phone if requested
    if send_phone:
        try:
            import jarvis
            if hasattr(jarvis, "phone_ref") and jarvis.phone_ref[0]:
                jarvis.phone_ref[0].push(report_text)
                print(f"[lead_hunter] Pushed {len(top_leads)} leads to paired phone.", flush=True)
        except Exception as e:
            print(f"[lead_hunter] Failed to push to phone: {e}", flush=True)

    return {
        "ok": True,
        "niche": niche,
        "location": loc,
        "count": len(top_leads),
        "leads": top_leads,
        "report": report_text
    }


def get_lead_hunter_prompt():
    """System prompt injection for Lead Hunter mode."""
    leads = get_saved_leads()
    lead_summary = f"{len(leads)} cached cold-pitch leads available" if leads else "No leads scanned yet"
    return f"""# ACTIVE MODE: Lead Hunter Mode (Client Traction & Local Business Scout)
You are an expert B2B Client Acquisition, Web Audit, and Lead Generation Agent.
Your mission:
1. Locate local small businesses in the user's area (default: Bucharest or configured home city) based on keywords (e.g. gym, dentist, plumber, auto repair, lawyer, salon).
2. Audit their websites and client traction: check if the site is missing entirely, lacks mobile viewport, has no SSL certificate, lacks analytics tracking, has outdated copyright, or has zero social links.
3. Enforce strict 2020+ recency: filter out obsolete businesses from prior to 2020.
4. Strictly verify website ownership: only retain businesses that have their own website (filter out directories, scrapers, and aggregators).
5. Attach direct Google Maps place listings so the user can inspect reviews, photos, and ratings with one click.
6. Rank them with the LOWEST client traction first (these are prime cold outreach prospects because they desperately need web design, SEO, and conversion optimization).
7. Provide structured lead cards with website links, Google Maps links, phone numbers, detected flaws, and tailored cold pitch hooks.
8. Use the `lead_hunter_scan` tool to perform live audits and automatically push leads to the user's phone.
Status: {lead_summary}."""


def generate_drip_sequence(lead_name_or_domain: str = "", issues: list = None) -> dict:
    """Auto-drafts a personalized 3-step cold email drip sequence referencing the business's actual site flaws."""
    leads = get_saved_leads()
    lead = None
    query = (lead_name_or_domain or "").strip().lower()
    if query:
        for l in leads:
            if query in l.get("name", "").lower() or query in l.get("url", "").lower():
                lead = l
                break

    if not lead and leads:
        lead = leads[0]
    elif not lead:
        lead = {
            "name": lead_name_or_domain or "Local Business",
            "url": "https://example.com",
            "niche": "Local Services",
            "location": resolve_location(),
            "issues": issues or ["No mobile viewport meta tag", "Missing SSL HTTPS certificate", "Slow response time (>2.4s)"],
            "traction_score": 35
        }

    name = lead.get("name", "Team")
    url = lead.get("url", "")
    niche = lead.get("niche", "business")
    loc = lead.get("location", resolve_location())
    issues_list = issues or lead.get("issues", [])
    primary_issue = issues_list[0] if issues_list else "outdated mobile layout"
    secondary_issue = issues_list[1] if len(issues_list) > 1 else "slow response speed"

    emails = [
        {
            "step": 1,
            "day": "Day 0 (Initial Outreach)",
            "subject": f"Quick question regarding {name}'s mobile site",
            "body": (
                f"Hi {name} team,\n\n"
                f"I was searching for top-rated {niche} in {loc} on my phone and came across {name}.\n\n"
                f"While checking out your site ({url}), I noticed a quick technical leak: {primary_issue}. "
                f"On smartphones, this causes high bounce rates because visitors struggle to view the menu/services.\n\n"
                f"Also, notice {secondary_issue} is hurting your local search ranking against nearby competitors.\n\n"
                f"I put together a 90-second screen recording showing exactly where visitors are dropping off and how to fix it in an afternoon. "
                f"Mind if I send the video over?\n\n"
                f"Best regards,\n[Your Name]"
            )
        },
        {
            "step": 2,
            "day": "Day 3 (Value Bump & Competitor Contrast)",
            "subject": f"Idea for {name} ({niche} in {loc})",
            "body": (
                f"Hi {name} team,\n\n"
                f"Following up on my note from Tuesday regarding {url}.\n\n"
                f"Nearby {niche} in {loc} that implemented fast mobile booking saw a noticeable bump in customer inquiries because "
                f"over 70% of local searches happen directly on mobile devices.\n\n"
                f"I sketched a lightweight prototype for {name} that resolves the {primary_issue} and adds one-tap WhatsApp / call booking.\n\n"
                f"Would you be opposed to taking a look at the mockup this week?\n\n"
                f"Best,\n[Your Name]"
            )
        },
        {
            "step": 3,
            "day": "Day 7 (Low-friction Break-up)",
            "subject": f"Permission to close your file? / {name}",
            "body": (
                f"Hi {name} team,\n\n"
                f"I haven't heard back, so I assume modernizing {url}'s web experience isn't a priority right now—totally understand.\n\n"
                f"If you ever decide to address the {primary_issue} so you don't leak mobile leads to competitors, feel free to reach back out.\n\n"
                f"Wishing {name} continued success in {loc}!\n\n"
                f"Best,\n[Your Name]"
            )
        }
    ]

    report = [
        f"✉️ **3-Step Cold Drip Sequence for {name}**",
        f"*Target:* `{url}` · *Niche:* `{niche}` · *Detected Flaws:* {', '.join(issues_list[:2])}\n"
    ]
    for em in emails:
        report.append(f"### {em['day']}: `{em['subject']}`")
        report.append(f"```text\n{em['body']}\n```\n")

    return {
        "ok": True,
        "lead": name,
        "url": url,
        "sequence": emails,
        "report": "\n".join(report)
    }


def reengage_scan(lead_name_or_domain: str = "") -> dict:
    """Re-audits previously saved leads to detect status changes (fixes or new degradations) as outreach timing hooks."""
    leads = get_saved_leads()
    if not leads:
        return {"ok": False, "error": "No saved leads found in database. Run lead_hunter_scan first."}

    targets = []
    query = (lead_name_or_domain or "").strip().lower()
    if query:
        targets = [l for l in leads if query in l.get("name", "").lower() or query in l.get("url", "").lower()]
    if not targets:
        targets = leads[:5]

    updates = []
    lines = [f"🔄 **Lead Re-engagement Scanner: Auditing {len(targets)} Saved Leads**\n"]

    for lead in targets:
        url = lead.get("url")
        if not url or url == "No Website":
            continue
        old_issues = set(lead.get("issues", []))
        new_audit = audit_website(url)
        new_issues = set(new_audit.get("issues", []))

        fixed = list(old_issues - new_issues)
        regressed = list(new_issues - old_issues)

        status_change = "unchanged"
        timing_hook = "Still has unaddressed leaks. Re-send follow up."
        if fixed:
            status_change = "improved"
            timing_hook = f"Active redesign detected! They resolved: {', '.join(fixed)}. Pitch remaining conversion gaps now before budget freezes."
        elif regressed:
            status_change = "degraded"
            timing_hook = f"Urgent leak alert: site health degraded ({', '.join(regressed)}). Great opening for incident alert cold outreach."

        # Update saved lead state
        lead["issues"] = new_audit.get("issues", [])
        lead["ssl"] = new_audit.get("ssl", False)
        lead["mobile_viewport"] = new_audit.get("mobile_viewport", False)
        lead["response_time_ms"] = new_audit.get("response_time_ms", 0)
        lead["last_reengage_scan"] = time.time()
        lead["status_change"] = status_change

        updates.append({
            "name": lead.get("name"),
            "url": url,
            "status_change": status_change,
            "fixed": fixed,
            "regressed": regressed,
            "timing_hook": timing_hook
        })

        badge = "🟢 IMPROVED" if status_change == "improved" else ("🔴 DEGRADED" if status_change == "degraded" else "⚪ UNCHANGED")
        lines.append(f"**{lead.get('name')}** ({lead.get('niche', 'business')}) — {badge}")
        lines.append(f"- 🌐 **Site**: {url}")
        if fixed:
            lines.append(f"- ✅ **Resolved**: {', '.join(fixed)}")
        if regressed:
            lines.append(f"- ⚠️ **New Issues**: {', '.join(regressed)}")
        lines.append(f"- 🎯 **Timing Hook**: {timing_hook}\n")

    save_leads(leads)

    return {
        "ok": True,
        "audited_count": len(updates),
        "updates": updates,
        "report": "\n".join(lines)
    }


def competitor_radar(business_name: str, niche: str = "", location: str = "") -> dict:
    """Surfaces local competitor traction and compares website metrics to build an irresistible competitive pitch."""
    loc = resolve_location(location)
    niche_clean = niche.strip() if niche else "local business"
    query = f"{niche_clean} in {loc}"

    competitors = []
    try:
        ddgs = DDGS()
        raw = list(ddgs.text(query, max_results=8))
        for r in raw:
            u = r.get("href") or r.get("link", "")
            title = r.get("title", "")
            if is_own_website(u):
                name = clean_business_name(title)
                if name.lower() != business_name.lower():
                    competitors.append({"name": name, "url": u})
            if len(competitors) >= 3:
                break
    except Exception as e:
        print(f"[lead_hunter] competitor search failed: {e}", flush=True)

    # Audit competitors
    comp_audits = []
    for comp in competitors:
        aud = audit_website(comp["url"])
        comp_audits.append({
            "name": comp["name"],
            "url": comp["url"],
            "ssl": aud.get("ssl", False),
            "mobile": aud.get("mobile_viewport", False),
            "speed_ms": aud.get("response_time_ms", 0),
            "issue_count": len(aud.get("issues", []))
        })

    report_lines = [
        f"📡 **Local Competitor Radar: {business_name} vs Top Competitors**",
        f"*Sector:* `{niche_clean}` in `{loc}`\n",
        "| Business | Mobile Ready | SSL Active | Response Speed | Health |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]

    for ca in comp_audits:
        m_icon = "✅ Yes" if ca["mobile"] else "❌ No"
        s_icon = "✅ Active" if ca["ssl"] else "❌ Missing"
        health = "🟢 Strong" if ca["issue_count"] <= 1 else "🟡 Moderate"
        report_lines.append(f"| **{ca['name']}** | {m_icon} | {s_icon} | {ca['speed_ms']}ms | {health} |")

    report_lines.append("\n💡 **Pitch Wedge Strategy:**")
    fastest = min(comp_audits, key=lambda x: x["speed_ms"]) if comp_audits else None
    if fastest and fastest["mobile"]:
        report_lines.append(
            f"Show `{business_name}` that `{fastest['name']}` loads in {fastest['speed_ms']}ms with full mobile responsiveness. "
            f"Pitch: 'Your top competitor {fastest['name']} is winning mobile searchers in {loc}. "
            f"Here is how we close the technical gap and win back customers.'"
        )
    else:
        report_lines.append(f"Competitors in {loc} also suffer from weak mobile optimization. First mover advantage available!")

    return {
        "ok": True,
        "business": business_name,
        "niche": niche_clean,
        "location": loc,
        "competitors": comp_audits,
        "report": "\n".join(report_lines)
    }
