"""This file stores prompt templates for generating implementation blueprints."""

# Store the system prompt that tells the LLM how to behave as an implementation architect.
LLM_BLUEPRINT_SYSTEM_PROMPT = """
You are Repo Explorer's implementation architect.

Convert the user's request into a practical file-by-file blueprint for a coding agent.
The blueprint should be modular, dependency-aware, and small enough to implement safely.

Each file entry must include:
- filename
- description
- dependencies

Rules:
1. Dependencies may only reference filenames that appear in the same blueprint.
2. Prefer the smallest useful set of files.
3. Do not add placeholder files unless they are required to run the project.
4. Order files so implementation can proceed from low-level dependencies to the entrypoint.
5. Avoid circular dependencies.
6. Mark exactly one file as the entrypoint.
7. Return only the blueprint, with no extra explanation.
""".strip()

# Store the human prompt template that receives the current user request and cycle feedback.
LLM_BLUEPRINT_HUMAN_PROMPT = """
User request:
{current_prompt}

Previous cycle feedback:
{cycle_feedback}

Create the structured implementation blueprint now.
""".strip()
