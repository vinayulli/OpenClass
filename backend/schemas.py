from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class Concept(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    prerequisites: list[str] = Field(default_factory=list, max_length=50)


class CourseInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    code: str = Field(default="COURSE", max_length=30)
    objectives: list[str] = Field(min_length=1, max_length=50)
    concepts: list[Concept] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def graph(self):
        ids = {c.id for c in self.concepts}
        if len(ids) != len(self.concepts):
            raise ValueError("Concept identifiers must be unique")
        edges = {c.id: c.prerequisites for c in self.concepts}
        def visit(node, path):
            if node in path:
                raise ValueError("Concept prerequisites must not contain cycles")
            for parent in edges[node]:
                if parent not in ids:
                    raise ValueError("Unknown prerequisite")
                visit(parent, path | {node})
        for node in ids:
            visit(node, set())
        return self


class Enrollment(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256)


class Material(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=40000)


class Blueprint(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    kind: Literal["practice", "diagnostic", "revision", "mock", "formal"] = "practice"
    concept_ids: list[str] = Field(min_length=1, max_length=50)
    question_count: int = Field(default=5, ge=1, le=20)
    total_marks: int = Field(default=10, ge=1, le=200)
    duration_minutes: int = Field(default=20, ge=1, le=180)
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    question_types: list[Literal["mcq", "short_answer", "coding"]] = Field(default_factory=lambda: ["mcq"], min_length=1)
    release_feedback: bool = True
    student_id: str | None = None

    @model_validator(mode="after")
    def coverage(self):
        if self.total_marks < self.question_count or self.question_count < len(self.concept_ids):
            raise ValueError("Provide at least one mark per question and one question per selected concept")
        if self.kind == "formal" and self.student_id:
            raise ValueError("Formal exams use a common blueprint, without individual personalization")
        return self


class Question(BaseModel):
    id: str
    prompt: str = Field(min_length=8, max_length=5000)
    type: Literal["mcq", "short_answer", "coding"]
    concept_id: str
    objective: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    marks: int = Field(ge=1, le=200)
    options: list[str] = Field(default_factory=list)
    answer: str = Field(min_length=1)
    rubric: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    material_id: str

    @model_validator(mode="after")
    def choices(self):
        if self.type == "mcq" and (len(self.options) < 2 or len(set(self.options)) != len(self.options) or self.answer not in self.options):
            raise ValueError("MCQ requires distinct choices and an answer contained in choices")
        return self


class ExamOutput(BaseModel):
    questions: list[Question]


class Answers(BaseModel):
    answers: dict[str, str] = Field(max_length=20)


class Chat(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    student_id: str | None = None
    student_ids: list[str] = Field(default_factory=list, max_length=50)


class AssessmentBatch(BaseModel):
    student_ids: list[str] = Field(min_length=1, max_length=50)
    blueprint: Blueprint | None = None
    teacher_request: str = Field(default="Generate personalized practice tests focused on evidenced gaps.", max_length=4000)


class InterventionOutput(BaseModel):
    title: str
    concept_id: str
    rationale: str
    lesson: str
    exercise: str
    success_criteria: str


class ReviewGrade(BaseModel):
    scores: dict[str, float]
    reason: str = Field(min_length=5, max_length=2000)


class RepoInput(BaseModel):
    url: str = Field(max_length=500)


class CodeOutput(BaseModel):
    summary: str
    demonstrated_skills: list[str]
    gaps: list[str]
    references: list[str]
    confidence: Literal["low", "medium", "high"]
    provisional_rating: int | None = Field(default=None, ge=0, le=100, description="AI estimate of the supplied code sample, not a final course grade; null when insufficient evidence")
    rating_rationale: str = "Insufficient detail to rate; educator review required"


class ExamAudience(BaseModel):
    student_ids: list[str] = Field(default_factory=list, max_length=200)


class ManualExam(BaseModel):
    blueprint: Blueprint
    questions: list[Question] = Field(min_length=1, max_length=20)
    student_ids: list[str] = Field(default_factory=list, max_length=200)


class CodingAssignment(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    instructions: str = Field(min_length=10, max_length=6000)
    concept_ids: list[str] = Field(min_length=1, max_length=50)
    student_ids: list[str] = Field(default_factory=list, max_length=200)


class CodeSubmission(RepoInput):
    assignment_id: str


class TwinSimulation(BaseModel):
    concept_id: str
    action: Literal["lesson_only", "practice", "reassessment"] = "reassessment"
    assumed_score: float = Field(default=.8, ge=0, le=1)
    observations: int = Field(default=3, ge=1, le=10)
