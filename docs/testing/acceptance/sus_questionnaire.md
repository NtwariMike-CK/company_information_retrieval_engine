# System Usability Scale (SUS) questionnaire

Give this to each participant **after** they finish the task list. Each statement is answered 1 (strongly disagree) to 5 (strongly agree).

| # | Statement |
|---|-----------|
| 1 | I think that I would like to use this system frequently. |
| 2 | I found the system unnecessarily complex. |
| 3 | I thought the system was easy to use. |
| 4 | I think that I would need the support of a technical person to be able to use this system. |
| 5 | I found the various functions in this system were well integrated. |
| 6 | I thought there was too much inconsistency in this system. |
| 7 | I would imagine that most people would learn to use this system very quickly. |
| 8 | I found the system very cumbersome to use. |
| 9 | I felt very confident using the system. |
| 10 | I needed to learn a lot of things before I could get going with this system. |

## Scoring rule (Brooke, 1996)
- Odd statements (1,3,5,7,9): contribution = answer - 1.
- Even statements (2,4,6,8,10): contribution = 5 - answer.
- SUS = (sum of the ten contributions) x 2.5, giving 0-100. **68 is the commonly used average; above 80 is excellent.**
- `sus_score.py` does this for the whole cohort.

## Extra questions for this project (survey analysis)
Scale 1-5 unless stated.
- S1 The answers matched what is written in the company documents.
- S2 I could ask in English and in Kinyarwanda and get a useful reply.
- S3 The "Searching company documents..." indicator made waiting acceptable.
- S4 Uploading a document and seeing it become ready was clear (Company Admin only).
- S5 Overall, I would trust this assistant for everyday workplace questions.
- S6 (open) What was the most confusing moment?
- S7 (open) What one thing would you change first?

## Task list for participants (about 15 minutes)
**Employee:** 1) log in; 2) start a new chat; 3) ask a question whose answer is in the documents; 4) ask a follow-up; 5) ask something NOT in the documents; 6) ask in Kinyarwanda; 7) rate an answer; 8) send a report.
**Company Admin:** 1) log in; 2) upload a document and watch processing; 3) add an employee; 4) Start the assistant; 5) open Analytics and export the questions report; 6) read a conversation.
