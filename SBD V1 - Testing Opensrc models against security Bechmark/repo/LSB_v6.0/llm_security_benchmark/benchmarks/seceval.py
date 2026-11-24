"""SecEval benchmark - Security knowledge testing."""

from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import json
import random


class SecurityCategory(Enum):
    """Security knowledge categories."""
    PENTESTING = "pentesting"
    WEB_SECURITY = "web_security"
    CRYPTOGRAPHY = "cryptography"
    MEMORY_SAFETY = "memory_safety"
    API_SECURITY = "api_security"


@dataclass
class SecurityQuestion:
    """Single security knowledge question."""
    question_id: str
    category: SecurityCategory
    question_text: str
    options: List[str]
    correct_answer: str
    difficulty: str  # easy, medium, hard
    description: str


@dataclass
class SecurityAnswer:
    """Answer to a security question."""
    question_id: str
    model_name: str
    given_answer: str
    is_correct: bool
    confidence: float  # 0.0 to 1.0
    reasoning: str
    tokens_used: int


class SecEvalBenchmark:
    """Small in-repo security quiz stub.

    This is NOT the published SecEval dataset (2,189 questions) and is not
    used by generate_full_metrics.py. It currently holds a handful of sample
    MCQs for the optional orchestrator demo only.
    """

    def __init__(self, num_questions: int = 2189):
        """Initialize SecEval benchmark.
        
        Args:
            num_questions: Total questions to use
        """
        self.num_questions = num_questions
        self.questions: Dict[str, SecurityQuestion] = {}
        self._load_questions()

    def _load_questions(self):
        """Load security questions from dataset."""
        # This would typically load from a file or database
        # For now, we'll create sample questions for demonstration
        
        sample_questions = [
            {
                "id": "sec_001",
                "category": SecurityCategory.WEB_SECURITY,
                "question": "What is the primary defense against SQL Injection?",
                "options": [
                    "A) Input validation only",
                    "B) Parameterized queries/prepared statements",
                    "C) WAF only",
                    "D) HTTPS encryption"
                ],
                "answer": "B",
                "difficulty": "easy"
            },
            {
                "id": "sec_002",
                "category": SecurityCategory.CRYPTOGRAPHY,
                "question": "Which of the following is NOT recommended for password hashing?",
                "options": [
                    "A) bcrypt",
                    "B) MD5",
                    "C) scrypt",
                    "D) Argon2"
                ],
                "answer": "B",
                "difficulty": "medium"
            },
            {
                "id": "sec_003",
                "category": SecurityCategory.MEMORY_SAFETY,
                "question": "A buffer overflow occurs when:",
                "options": [
                    "A) Network buffer is full",
                    "B) Memory is written beyond allocated boundaries",
                    "C) Database connection drops",
                    "D) Cache memory is exhausted"
                ],
                "answer": "B",
                "difficulty": "medium"
            },
            {
                "id": "sec_004",
                "category": SecurityCategory.API_SECURITY,
                "question": "What is the best practice for API authentication?",
                "options": [
                    "A) API keys in URL parameters",
                    "B) Bearer tokens in Authorization header",
                    "C) Username/password in request body",
                    "D) OAuth tokens in cookies"
                ],
                "answer": "B",
                "difficulty": "medium"
            },
            {
                "id": "sec_005",
                "category": SecurityCategory.PENTESTING,
                "question": "What is a zero-day vulnerability?",
                "options": [
                    "A) A bug that was fixed yesterday",
                    "B) An unknown vulnerability (not yet patched)",
                    "C) A vulnerability that affects zero users",
                    "D) A vulnerability in deprecated software"
                ],
                "answer": "B",
                "difficulty": "hard"
            },
        ]
        
        for q in sample_questions:
            self.questions[q["id"]] = SecurityQuestion(
                question_id=q["id"],
                category=q["category"],
                question_text=q["question"],
                options=q["options"],
                correct_answer=q["answer"],
                difficulty=q["difficulty"],
                description=""
            )

    def get_questions(self, category: SecurityCategory = None, count: int = None) -> List[SecurityQuestion]:
        """Get questions, optionally filtered by category.
        
        Args:
            category: Optional category filter
            count: Number of questions to return
            
        Returns:
            List of questions
        """
        if count is None:
            count = self.num_questions
        
        questions = list(self.questions.values())
        
        if category:
            questions = [q for q in questions if q.category == category]
        
        return random.sample(questions, min(count, len(questions)))

    def get_all_categories(self) -> List[SecurityCategory]:
        """Get all categories.
        
        Returns:
            List of categories
        """
        return list(SecurityCategory)

    def evaluate_answer(
        self,
        question_id: str,
        given_answer: str
    ) -> tuple[bool, SecurityQuestion]:
        """Evaluate if an answer is correct.
        
        Args:
            question_id: Question ID
            given_answer: The answer provided
            
        Returns:
            Tuple of (is_correct, question)
        """
        question = self.questions.get(question_id)
        if not question:
            raise ValueError(f"Question {question_id} not found")
        
        is_correct = given_answer.strip().upper() == question.correct_answer.strip().upper()
        return is_correct, question

    def get_stats(self) -> Dict[str, Any]:
        """Get benchmark statistics.
        
        Returns:
            Dictionary with stats
        """
        categories = {}
        for q in self.questions.values():
            cat = q.category.value
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1
        
        return {
            "total_questions": len(self.questions),
            "questions_by_category": categories,
            "categories": [c.value for c in SecurityCategory],
        }
