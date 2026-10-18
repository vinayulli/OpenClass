# OpenClass: three-minute working demo

Use only synthetic demo accounts and show the actual deployed behavior. Record
after live agent acceptance checks pass. Keep API keys, tokens, browser cookies,
cloud credentials and terminal environment files out of the recording.

| Time | Screen and action | Explain |
|---|---|---|
| 0:00–0:20 | Teacher dashboard: Machine Learning classroom | Ten learners with different strengths; 70% of the syllabus has been taught. Teachers need evidence-based next steps for each learner. |
| 0:20–0:50 | Select a learner and open their detailed progress | Show an evidenced strength, a specific gap and submitted work. Distinguish recorded evidence from an inferred recommendation. |
| 0:50–1:25 | Ask Classroom Advisor to generate a short targeted assessment | Show the specialist task, its status and the completed assessment link. Generation is asynchronous; use a visible edit if waiting would dominate the video. |
| 1:25–1:55 | Log out; sign in as the selected learner | Open the assessment notification, take the test and submit. Show the actual completion result. |
| 1:55–2:30 | Learning Coach | Ask for progress and an explanation of a weak concept. Show the rendered answer, conversation session and honest memory status. |
| 2:30–2:50 | Learning path | Show concrete next actions and reference links. If regeneration is demonstrated, show a completed generated plan. |
| 2:50–3:00 | Architecture diagram / closing screen | React and FastAPI, PostgreSQL evidence, Gemini specialists, learner memory, separated MCP services and content protection. Name only the hosting/security services verified in the final deployment. |

## Before recording

- Confirm the public application URL works in an incognito browser.
- Verify the intended teacher and student accounts can load the classroom.
- Generate one completed assessment and one detailed learning plan as backups.
- Check notifications, assessment submission and Coach response with those accounts.
- Confirm no unrelated local development worker is competing for the cloud task queue.
- Keep a completed generation visible if a live model call is slow; describe any edit honestly.
- Show synthetic data as synthetic. Show counterfactual learning scenarios as simulations.
- Verify the submission dashboard's current video and accessibility requirements.

The published challenge requests a three-minute public video and emphasizes
meaningful AI implementation, impact, innovation and user experience:
[AI Builder Cup requirements](https://aibuildercup.com/themes.html).

If specialist hosting falls back to Cloud Run, show that architecture accurately.
Agent Gateway egress enforcement must not be claimed for Cloud Run specialists
unless its routing and denial tests were independently demonstrated.
