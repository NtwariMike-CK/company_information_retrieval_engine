"""Default content. Seeded into the database ONCE (only when the table is empty); afterwards the SuperAdmin edits it in the UI."""

EN_STOP = ("the a an of and or to in on for with at by from as is are was were be been it its this that these those i you he she we "
           "they my your our their me us them what which who whom when where why how do does did can could will would should not no "
           "so if then than there here about into over under also").split()
RW_STOP = ("na ni mu ku kuri kuva ya yo ye wa wo ba bo bwa bwo cya cyo ry rya ryo rw rwa rwo za zo ze y w z b k n mw bya byo ka ko ke "
           "ga ho aho hari hano aha uru uyu uwo uwa urwo iyi iyo iki icyo ibi ibyo aba abo abandi aya ayo ubu ubwo kandi ariko cyangwa "
           "kuko kubera nyuma mbere nka nk nta ntabwo niba ngo kugira kuba kwa uko buri bose byose yose zose bwose cyose rwose twe mwe "
           "jye wowe ndetse hamwe kugeza igihe akaba ubwa").split()
RW_STOP = sorted(set(RW_STOP) - set(EN_STOP))       # words must not count for both languages

LANGUAGES = [
    dict(code="en", name="English", native_name="English", position=1, stopwords=sorted(set(EN_STOP)),
         sample_text=None, sample_text_en=None, sample_question=None),
    dict(code="rw", name="Kinyarwanda", native_name="Ikinyarwanda", position=2, stopwords=RW_STOP,
         sample_text="Abakozi bemerewe iminsi makumyabiri n'itanu y'ikiruhuko buri mwaka.",
         sample_text_en="Employees are entitled to twenty-five days of leave every year.",
         sample_question="Abakozi bemerewe iminsi ingahe y'ikiruhuko buri mwaka?"),
]

SITE_CONTENT = [
    ("hero", "Hero", 1, dict(
        title="Your company's knowledge, one question away",
        subtitle="An AI assistant that answers your employees' questions from your own documents, in English and Kinyarwanda. "
                 "Private to your company, simple to set up, fully under your control.",
        body="", items=[])),
    ("highlights", "Highlights strip", 2, dict(title="", subtitle="", body="", items=[
        dict(title="English & Kinyarwanda", text="Ask in one language, find answers in documents written in the other.", icon="Languages"),
        dict(title="Grounded answers", text="Replies come from your documents. When something is missing, it says so.", icon="FileText"),
        dict(title="Private by design", text="Each company's data is isolated from every other company.", icon="ShieldCheck"),
        dict(title="You stay in control", text="Start, pause or end the service at any time.", icon="KeyRound")])),
    ("features", "Features", 3, dict(
        title="Everything your team needs to find answers fast",
        subtitle="Stop searching through folders and chat history. Let employees simply ask.", body="", items=[
            dict(title="Ask in plain language", text="Employees type a question the way they would ask a colleague and get a clear answer with the source document.", icon="MessageSquare"),
            dict(title="Works with your files", text="Upload PDF, Word, text and Markdown documents. They are prepared and indexed automatically.", icon="FileText"),
            dict(title="Bilingual search", text="Questions and documents can be in English or Kinyarwanda. The assistant matches meaning, not just keywords.", icon="Languages"),
            dict(title="Your own team", text="Add your employees, activate or deactivate access, and review how the assistant is used.", icon="Users"),
            dict(title="Insight and feedback", text="See the most frequent questions, which ones had no answer in your documents, and how employees rate the replies.", icon="BarChart3"),
            dict(title="Download your data", text="Export your documents, conversations and reports whenever you want.", icon="Database")])),
    ("how_it_works", "How it works", 4, dict(
        title="From request to first answer", subtitle="A short, guided process.", body="", items=[
            dict(title="Create your account", text="Register with your name, phone and email.", icon="UserCheck"),
            dict(title="Request access", text="Tell us about your company and how you plan to use the assistant.", icon="ClipboardList"),
            dict(title="We review it", text="We approve, ask for more information, or explain why not. You reply right in the portal.", icon="CheckCircle2"),
            dict(title="Onboard in minutes", text="Read the data guidelines and privacy summary, then accept the terms.", icon="ShieldCheck"),
            dict(title="Upload and start", text="Add your documents and your employees, press Start, and the assistant is live.", icon="Rocket")])),
    ("languages", "Languages", 5, dict(
        title="Built for English and Kinyarwanda",
        subtitle="Your documents and your people do not all work in one language.",
        body="Employees can ask in English or Kinyarwanda, and the answer comes back in the language of the question, even when the source document is written in the other one. "
             "More African languages can be added over time.", items=[
            dict(title="Ask in Kinyarwanda, answer from English documents", text="", icon="Globe"),
            dict(title="Ask in English, answer from Kinyarwanda documents", text="", icon="Globe"),
            dict(title="Honest when information is missing", text="The assistant tells the employee in their own language when the documents do not cover the question.", icon="Search")])),
    ("security", "Privacy & security", 6, dict(
        title="Your data stays yours",
        subtitle="Clear rules, shown to you before you start.", body="", items=[
            dict(title="Isolated per company", text="No other company can see your documents, conversations or reports.", icon="Lock"),
            dict(title="You control access", text="Your administrators decide who can use the assistant and can review conversations.", icon="UserCheck"),
            dict(title="Deleted when you leave", text="When you end the service, your documents, conversations, feedback and employee accounts are permanently deleted.", icon="Trash2"),
            dict(title="Take it with you", text="Download your data before you end the service.", icon="Database")])),
    ("faq", "FAQ", 7, dict(title="Frequently asked questions", subtitle="", body="", items=[
        dict(title="Who can request access?", text="Any organisation, from small businesses to large companies. Every request is reviewed manually before approval.", icon=""),
        dict(title="Which documents can we upload?", text="PDF (with selectable text), Word (.docx), plain text and Markdown. Well-formatted documents with clear headings give the best answers.", icon=""),
        dict(title="Can the assistant make mistakes?", text="Yes. It answers from your documents and says when it cannot find the information, but answers should still be checked for important decisions. Employees can rate answers and report problems.", icon=""),
        dict(title="What happens to our data if we stop?", text="Pressing End service permanently deletes your documents, conversations, feedback, reports and employee accounts. We recommend downloading your data first.", icon=""),
        dict(title="Do you use our documents to train AI?", text="We do not use your documents to build our own models. Only anonymous ratings and report categories, with no company, person or text attached, are kept to improve the service. Read the full privacy summary and terms below.", icon=""),
        dict(title="Does it cost anything?", text="Access is currently by request. Usage-based pricing is planned for the future and will be communicated before it applies.", icon="")])),
    ("cta", "Final call to action", 8, dict(
        title="Ready to give your team instant answers?",
        subtitle="Create an account and tell us about your company. Reviews are done by our team.", body="", items=[])),
]

STEPS = [
    ("data_guidelines", 1, False, "Prepare your documents", """## Before you upload

The assistant can only answer from the documents you give it, so a little preparation makes a big difference.

### Accepted formats
- **PDF**: must contain selectable text. Scanned images are not read yet.
- **Word** (.docx)
- **Plain text** (.txt) and **Markdown** (.md)

### Languages
Documents and questions can be written in **English**, **Kinyarwanda**, or both. An employee can ask in one language and receive an answer based on documents written in the other.

### How to format documents for good results
- Use **clear headings** and short paragraphs. One topic per section.
- Prefer one subject per document (for example "Leave policy", "Expense procedure").
- Keep documents **current**. Remove outdated versions so old rules are not quoted.
- Write names, amounts, dates and acronyms clearly and consistently.
- Avoid scanned pages and photographs of text. Use the original digital file when you can.
- Do not upload passwords, bank details or other secrets.

> **Note:** a well formatted document will produce good results. Poorly formatted files lead to weaker answers.

### Recommended: an employee onboarding guide
Prepare documentation that takes a new employee from beginner to expert: policies, procedures, tools and frequently asked questions. Use it to train your team, then upload it so the assistant can answer from it. Training your employees is your company's responsibility; the platform does not provide it.

### Not supported yet
Images and screenshots inside documents are not interpreted at this time."""),
    ("privacy_summary", 2, False, "How we protect your data", """## Privacy summary

### Your data is separate from every other company's
Each company has its own private knowledge base. No other company can access your documents, conversations or reports.

### Who can see what
- **Your company administrators** can see all uploaded documents, employee questions, answers, ratings and reports, and can download them.
- **Your employees** see answers to their own questions and their own chat history.
- **Platform administrators** do not browse company data. They may open a company workspace only to provide support or maintain the service, and every such access is recorded in an audit log.

### How your data is processed
To answer a question, the platform sends the question and the most relevant passages of your documents to an AI service provided by **Google (Gemini API)**. The text of your documents is also converted into numerical representations (embeddings) by the same provider. Google acts as a service provider for this processing.

### Where your data is stored
The application runs on **Render** (backend and database) and **Vercel** (website). Uploaded files and processed text are stored in this cloud infrastructure and nowhere else.

### When you end the service
Pressing **End service** permanently deletes your uploaded documents, extracted text, chunks and embeddings, conversations, feedback, reported cases and employee accounts. **Download your data before ending the service**: after deletion it cannot be restored. Database backups held by the hosting provider expire automatically according to its retention schedule.

### Anonymous improvement data
When you give feedback or report a problem, a de-identified record (the rating or report category and the month) may be kept to improve the service. It contains no company name, no person, and none of your questions, answers or documents."""),
    ("terms", 3, True, "Terms & conditions", """## Terms & conditions

*By accepting, you confirm that you are authorised to accept these terms on behalf of your company.*

**1. The service.** The platform lets your company upload documents and lets your employees ask questions that are answered from those documents by an AI assistant.

**2. Your account and your employees.** You are responsible for the accounts you create, for keeping credentials safe, and for deactivating accounts of people who leave.

**3. Your content.** You confirm that you have the right to upload the documents you provide and that they do not break the law or the rights of others. Do not upload information you are not allowed to share with a service provider. Avoid unnecessary personal data.

**4. Data isolation and access.** Your data is kept separate from other companies' data. Your administrators have full access to your company's documents, conversations and reports. Platform administrators access company data only for support and maintenance, and that access is logged.

**5. AI processing.** To provide answers, text from your documents and your employees' questions is processed by Google's Gemini API. The platform is hosted on Render and Vercel. These providers process data only to deliver the service.

**6. Accuracy.** Answers are generated by AI from your documents and may be incomplete or wrong. They must not be your only basis for legal, medical, financial or safety decisions. Employees can rate answers and report problems.

**7. Ending the service and deletion.** You may pause the service at any time without losing data. When you end the service, all of your documents, processed data, conversations, feedback, reports and employee accounts are permanently deleted and cannot be recovered. You are advised to download your data first.

**8. Feedback and reports.** Feedback ratings and report categories may be kept in anonymised form, without any company, person, question, answer or document, to improve the service.

**9. Acceptable use.** You will not misuse the service, attempt to access other companies' data, overload the platform, or use it for unlawful purposes. We may suspend access that breaks these terms.

**10. Availability.** The service is provided on a best-effort basis and may be interrupted for maintenance or because of third-party outages.

**11. Changes.** We may update these terms. When they change, you will be asked to review and accept the new version, and the version you accepted is recorded.

**12. Contact.** For questions about these terms or your data, contact the platform team through your portal."""),
]

FORM_FIELDS = [
    ("company_name", "Company name", None, "text", [], True, True, 1),
    ("industry", "Industry", None, "select", ["Agriculture", "Banking & finance", "Education", "Government & public sector", "Healthcare",
                                              "Hospitality & tourism", "Manufacturing", "NGO / non-profit", "Retail & commerce",
                                              "Technology & telecom", "Transport & logistics", "Other"], True, False, 2),
    ("services", "What products or services does your company provide?", "A short description of what your company does.", "textarea", [], True, False, 3),
    ("country", "Country", None, "text", [], True, False, 4),
    ("city", "City / district", None, "text", [], True, False, 5),
    ("employee_count", "How many employees will use the assistant?", "An estimate is fine.", "number", [], True, False, 6),
    ("document_languages", "In which languages are your documents written?", None, "multiselect", ["English", "Kinyarwanda", "Other"], True, False, 7),
    ("intended_use", "What will employees use the assistant for?", "For example: HR policies, procedures, product manuals, training material.", "textarea", [], True, False, 8),
    ("website", "Website (optional)", None, "text", [], False, False, 9),
    ("additional_info", "Anything else we should know? (optional)", None, "textarea", [], False, False, 10),
]
