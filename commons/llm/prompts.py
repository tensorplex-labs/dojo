from typing import List
from pydantic import BaseModel, validator

from template.protocol import Completion


# TODO place proper scoring prompt once JSON mode works
system_score_completion_prompt = """
You are a helpful assistant that provides responses in JSON. Your task is to score the quality of each of the completions with respect to a prompt, where your score must be in the range {range_lower} to {range_upper}, where {range_lower} is the lowest score and {range_upper} is the highest score, and a higher score represents a higher quality response. You must provide your answer in JSON format.
"""
user_score_completion_prompt = """
Prompt:
{prompt}

{completions_prompt}

Assistant:
"""

completion_item_prompt = """
Completion #{idx}
{text}
"""


# NOTE here you should either use ranges [0,1] or [1,10], do not use [-1,1] as LLMs will perform poorly
class ScoreRange(BaseModel):
    lower: int
    upper: int

    @validator("lower")
    def lower_must_be_less_than_upper(cls, v, values, **kwargs):
        if "upper" in values and v >= values["upper"]:
            raise ValueError("lower must be less than upper")
        return v


class PromptBuilder:
    @staticmethod
    def build_user_score_completion_prompt(prompt: str, completions: List[Completion]):
        if not len(completions):
            raise ValueError("Cannot build prompt without any completions")

        # score_range = ScoreRange(lower=1, upper=10)
        completion_prompts = [
            completion_item_prompt.format(idx=c.cid, text=c)
            for i, c in enumerate(completions)
        ]
        formatted_prompt = user_score_completion_prompt.format(
            # range_lower=score_range.lower,
            # range_upper=score_range.upper,
            prompt=prompt,
            completions_prompt="\n".join(completion_prompts),
        )
        print(f"User prompt:\n{formatted_prompt}")
        return formatted_prompt

    @staticmethod
    def build_system_score_completion_prompt(score_range: ScoreRange):
        formatted_prompt = system_score_completion_prompt.format(
            range_lower=score_range.lower, range_upper=score_range.upper
        )
        print("System prompt: \n", formatted_prompt)
        return formatted_prompt
