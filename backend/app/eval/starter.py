"""Starter benchmark dataset, seeded once. Three English/Kinyarwanda documents and 21 questions:
same-language, cross-language (English question / Kinyarwanda document and the reverse) and unanswerable questions.
The Kinyarwanda text was written by the developer and should be reviewed by a native speaker."""
from pathlib import Path

from psycopg.types.json import Jsonb

from ..db import ex, q1
from ..settings import settings

DATASET_NAME = "Starter benchmark: HR, IT security and office rules (EN + RW)"
DATASET_DESCRIPTION = ("Small bilingual benchmark: 17 answerable and 4 unanswerable questions over 4 documents. "
                       "Replace or extend it with your own company-style documents and questions.")

DOCS = {
 "hr_policy_en.md": ("en", """# Employee Handbook: Leave and Working Conditions

## Annual leave
Employees are entitled to twenty-five days of paid annual leave per year. Leave requests must be submitted at least two weeks in advance and approved by the line manager.

## Remote work
Employees may work remotely up to three days per week, with the prior approval of their line manager.

## Probation
The probation period for new employees is three months.

## Sick leave
Employees receive fifteen days of paid sick leave per year. A medical certificate is required for any absence longer than two days.

## Overtime
Approved overtime is paid at one and a half times the normal hourly rate.

## Resignation
An employee who wishes to resign must give thirty days' written notice.
"""),
 "it_security_en.md": ("en", """# IT Security Policy

## Passwords
Passwords must contain at least twelve characters. Passwords must be changed every ninety days.

## Multi-factor authentication
Multi-factor authentication is mandatory for all company email and VPN accounts.

## Devices
All company laptops must use full-disk encryption. Employees may not install unapproved software.

## Incidents
Any suspected security incident must be reported to the IT helpdesk within 24 hours.
"""),
 "hr_policy_rw.md": ("rw", """# Igitabo cy'abakozi: Ikiruhuko n'imikorere

## Ikiruhuko cy'umwaka
Abakozi bemerewe iminsi makumyabiri n'itanu y'ikiruhuko cyishyurwa buri mwaka. Umukozi asaba ikiruhuko mbere y'ibyumweru bibiri kandi umuyobozi we agomba kukiyemeza.

## Gukorera mu rugo
Abakozi bashobora gukorera mu rugo iminsi itatu mu cyumweru babiherewe uruhushya n'umuyobozi.

## Igihe cy'igeragezwa
Igihe cy'igeragezwa ni amezi atatu.

## Ikiruhuko cy'uburwayi
Ikiruhuko cy'uburwayi ni iminsi cumi n'itanu yishyurwa. Icyemezo cya muganga kirakenewe nyuma y'iminsi ibiri.

## Amasaha y'inyongera
Amasaha y'inyongera yishyurwa inshuro imwe n'igice y'umushahara usanzwe.

## Gusezera ku kazi
Umukozi wifuza gusezera atanga integuza y'iminsi mirongo itatu.
"""),
 "office_rules_rw.md": ("rw", """# Amabwiriza y'ibiro

## Amasaha y'akazi
Ibiro bifungura saa 08:00 bigafunga saa 17:00 kuva ku wa mbere kugeza ku wa gatanu.

## Parikingi
Parikingi y'abakozi iri ku igorofa rya kabiri.

## Ifunguro rya sasita
Ifunguro rya sasita ritangwa muri kantini kuva saa 12:30 kugeza saa 14:00.
"""),
}

# (question, question_language, document_language, answerable, expected_answer, evidence phrases, key facts)
CASES = [
 ("How many days of annual leave do employees get?", "en", "en", True, "Employees get twenty-five days of paid annual leave per year.", ["twenty-five days of paid annual leave per year"], ["25|twenty-five|twenty five"]),
 ("How many days per week can I work remotely?", "en", "en", True, "Up to three days per week, with line manager approval.", ["work remotely up to three days per week"], ["three|3"]),
 ("How long is the probation period?", "en", "en", True, "The probation period is three months.", ["probation period for new employees is three months"], ["three months|3 months"]),
 ("When do I need a medical certificate for sick leave?", "en", "en", True, "For any absence longer than two days.", ["A medical certificate is required for any absence longer than two days"], ["two days|2 days|longer than two"]),
 ("How is overtime paid?", "en", "en", True, "At one and a half times the normal hourly rate.", ["Approved overtime is paid at one and a half times the normal hourly rate"], ["one and a half|1.5"]),
 ("How much notice must I give when resigning?", "en", "en", True, "Thirty days' written notice.", ["must give thirty days' written notice"], ["thirty|30"]),
 ("What is the minimum password length?", "en", "en", True, "At least twelve characters.", ["Passwords must contain at least twelve characters"], ["twelve|12"]),
 ("Is multi-factor authentication required?", "en", "en", True, "Yes, it is mandatory for company email and VPN accounts.", ["Multi-factor authentication is mandatory for all company email and VPN accounts"], ["mandatory|required|yes"]),
 ("How quickly must a security incident be reported?", "en", "en", True, "Within 24 hours to the IT helpdesk.", ["reported to the IT helpdesk within 24 hours"], ["24 hours|twenty-four hours|24"]),
 ("Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka?", "rw", "rw", True, "Abakozi bemerewe iminsi makumyabiri n'itanu y'ikiruhuko cyishyurwa buri mwaka.", ["Abakozi bemerewe iminsi makumyabiri n'itanu y'ikiruhuko cyishyurwa buri mwaka"], ["makumyabiri n'itanu|25"]),
 ("Igihe cy'igeragezwa kimara igihe kingana iki?", "rw", "rw", True, "Igihe cy'igeragezwa ni amezi atatu.", ["Igihe cy'igeragezwa ni amezi atatu"], ["amezi atatu|3"]),
 ("Amasaha y'inyongera yishyurwa ate?", "rw", "rw", True, "Yishyurwa inshuro imwe n'igice y'umushahara usanzwe.", ["Amasaha y'inyongera yishyurwa inshuro imwe n'igice y'umushahara usanzwe"], ["inshuro imwe n'igice|1.5"]),
 ("What time does the office open?", "en", "rw", True, "The office opens at 08:00.", ["Ibiro bifungura saa 08:00 bigafunga saa 17:00"], ["08:00|8:00|8 am|8am"]),
 ("Where is the staff parking?", "en", "rw", True, "On the second floor.", ["Parikingi y'abakozi iri ku igorofa rya kabiri"], ["second floor|2nd floor|igorofa rya kabiri"]),
 ("When is lunch served in the canteen?", "en", "rw", True, "From 12:30 to 14:00.", ["Ifunguro rya sasita ritangwa muri kantini kuva saa 12:30 kugeza saa 14:00"], ["12:30"]),
 ("Ijambo ry'ibanga rigomba kuba rifite inyuguti zingahe nibura?", "rw", "en", True, "Nibura inyuguti cumi n'ebyiri.", ["Passwords must contain at least twelve characters"], ["12|cumi n'ebyiri|twelve"]),
 ("Ni mu masaha angahe ngomba gutanga raporo y'ikibazo cy'umutekano?", "rw", "en", True, "Mu masaha 24.", ["reported to the IT helpdesk within 24 hours"], ["24|makumyabiri na ane"]),
 ("What is the company's policy on bringing pets to the office?", "en", None, False, "The documents do not say.", [], []),
 ("Who is the CEO of the company?", "en", None, False, "The documents do not say.", [], []),
 ("Ni iyihe politiki y'ikigo ku bijyanye no kuzana amatungo mu biro?", "rw", None, False, "Inyandiko ntizibivuga.", [], []),
 ("What is the annual bonus percentage?", "en", None, False, "The documents do not say.", [], []),
]


async def ensure_starter_dataset(conn) -> bool:
    """Create the starter dataset if there is no dataset yet. Returns True when it was created."""
    if await q1(conn, "SELECT 1 FROM eval_datasets LIMIT 1"):
        return False
    ds = await q1(conn, "INSERT INTO eval_datasets (name, description, is_starter) VALUES (%s,%s,TRUE) RETURNING id", DATASET_NAME, DATASET_DESCRIPTION)
    company = await q1(conn, """INSERT INTO companies (name, is_system, access_status) VALUES (%s, TRUE, 'inactive') RETURNING id""", f"[System] Evaluation workspace {ds['id']}")
    await ex(conn, "UPDATE eval_datasets SET company_id=%s WHERE id=%s", company["id"], ds["id"])
    folder = Path(settings.storage_dir) / "_eval" / str(ds["id"])
    folder.mkdir(parents=True, exist_ok=True)
    for name, (lang, text) in DOCS.items():
        path = folder / name
        path.write_text(text, encoding="utf-8")
        await ex(conn, "INSERT INTO eval_documents (dataset_id, filename, file_type, language, storage_path, size_bytes) VALUES (%s,%s,%s,%s,%s,%s)",
                 ds["id"], name, name.rsplit(".", 1)[1], lang, str(path), len(text.encode()))
    for i, (question, qlang, dlang, answerable, expected, evidence, facts) in enumerate(CASES, 1):
        await ex(conn, """INSERT INTO eval_cases (dataset_id, position, question, question_language, document_language, answerable, expected_answer, evidence, key_facts)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", ds["id"], i, question, qlang, dlang, answerable, expected, Jsonb(evidence), Jsonb(facts))
    return True
