# Machine Learning demo

The default classroom is **Machine Learning: from data to decisions (ML 201)** at `/courses/machine-learning/overview`. Use `teacher@openclass.demo` or `student@openclass.demo`, password `OpenClass123!`. Other learners use `student2@openclass.demo` through `student10@openclass.demo` with the same demo password.

The teacher has taught **14 of 20 topics (70%)**. Teaching coverage is separate from student mastery and assessed evidence coverage. Taught topics include ML workflow, data quality, exploratory statistics, probability, splitting, preprocessing, linear/logistic regression, regression/classification metrics, nearest neighbors, decision trees, cross-validation and regularization. Ensembles, feature selection, clustering, PCA, neural networks and deployment are planned. No evidence is fabricated for planned topics, and they are labelled **not yet taught**, rather than learning gaps.

| Learner | Demonstration profile |
| --- | --- |
| Jamie | Strong implementation; needs evaluation discipline |
| Aarav | Strong statistics; developing implementation confidence |
| Maya | Balanced progress; ready for deeper error analysis |
| Sofia | Clear explanations; needs numerical metric practice |
| Noah | Advanced applied understanding; ready for challenging cases |
| Isha | Improving foundations; prefers short guided activities |
| Liam | Practical intuition; incomplete assessment coverage |
| Emma | Strong communication; needs independent reproducible experiments |
| Olivia | Strong evaluation; selective preprocessing gaps |
| Ethan | Recently joined; later taught topics need diagnostics |

These are handwritten synthetic academic profiles, not psychological assessments or live model conclusions. Their scores, coverage and feedback differ. The fixtures include three historical formative observations per assessed topic, three quizzes with graded attempts, two coding assignments, six provisional source reports, one failed submission example, ten detailed starter paths with official reference links, ten feedback records and Twin history. Planned topics and missing observations are not scored zero. Historical quiz examples are distinct from the formative evidence feeding the starter Twins.

`machine_learning.json` defines the syllabus and profiles; `machine_learning.py` constructs and imports the related records. Startup imports this dataset once in demo mode, using an import marker and pipelined writes. The old Python classroom is hidden from the class picker with an archive flag; its accounts and past work are preserved. Existing non-synthetic work cannot be overwritten by fixture IDs. No model or managed-memory calls are made during fixture import.

For manual import after application database initialization:

```powershell
uv run python -m mock_data.seed
uv run python -m mock_data.seed --apply
```

The older separate forty-learner `mock-academy` fixture pack is available only with `--legacy`. The default importer now uses Machine Learning.

Starter paths are explicitly labelled synthetic. Generate live plans from **AI learning plans** and individual student profiles. Their goals, lessons, exercises, checkpoints and reading guidance are expandable to keep the main screen concise. References use server-maintained resource IDs resolved to course materials and official documentation; the model does not invent URLs.
