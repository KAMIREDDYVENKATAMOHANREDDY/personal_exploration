# v_cycle_langgraph.py
#
# Requirements:
# pip install langgraph langchain-core llama-cpp-python
#
# Example:
# python v_cycle_langgraph.py
#
# NOTE:
# Replace MODEL_PATH with your local GGUF model path.

import json
import uuid
from datetime import datetime
from typing import TypedDict, List, Dict, Any

from llama_cpp import Llama
from langgraph.graph import StateGraph, END


MODEL_PATH = "models/gemma-3-27b-it-q4_k_m.gguf"


# -----------------------------
# Llama.cpp model initialization
# -----------------------------
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=8192,
    n_threads=8,
    n_gpu_layers=-1,
    verbose=False,
)


# -----------------------------
# Shared graph state
# -----------------------------
class VCycleState(TypedDict):
    requirement: str
    requirement_output: str
    test_output: str
    validation_output: str
    qa_output: str
    human_feedback: str
    approved: bool
    session_id: str
    history: List[Dict[str, Any]]


# -----------------------------
# Helper functions
# -----------------------------
def ask_llm(system_prompt: str, user_prompt: str) -> str:
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    return response["choices"][0]["message"]["content"]


def human_loop(stage: str, content: str) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(f"HUMAN REVIEW STAGE: {stage}")
    print("=" * 80)
    print(content)
    print("=" * 80)

    decision = input("Approve this stage? (yes/no): ").strip().lower()

    feedback = ""
    approved = decision == "yes"

    if not approved:
        feedback = input("Enter feedback for revision: ").strip()

    return {
        "approved": approved,
        "feedback": feedback,
    }


def append_history(state: VCycleState, agent: str, output: str):
    state["history"].append(
        {
            "agent": agent,
            "output": output,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


# -----------------------------
# Requirement Agent
# -----------------------------
def requirement_agent(state: VCycleState) -> VCycleState:
    prompt = f"""
You are a strict software requirement analyst.

User requirement:
{state['requirement']}

Generate:
1. Functional requirements
2. Non-functional requirements
3. Constraints
4. Acceptance criteria

Be concise and technical.
"""

    output = ask_llm(
        system_prompt="You are a requirement engineering expert.",
        user_prompt=prompt,
    )

    state["requirement_output"] = output
    append_history(state, "requirement_agent", output)

    review = human_loop("Requirement Agent", output)

    state["approved"] = review["approved"]
    state["human_feedback"] = review["feedback"]

    return state


# -----------------------------
# Test Agent
# -----------------------------
def test_agent(state: VCycleState) -> VCycleState:
    prompt = f"""
Based on these approved requirements:

{state['requirement_output']}

Generate:
1. Unit tests
2. Integration tests
3. Edge cases
4. Failure scenarios
5. Test matrix
"""

    output = ask_llm(
        system_prompt="You are a senior QA architect.",
        user_prompt=prompt,
    )

    state["test_output"] = output
    append_history(state, "test_agent", output)

    review = human_loop("Test Agent", output)

    state["approved"] = review["approved"]
    state["human_feedback"] = review["feedback"]

    return state


# -----------------------------
# Validation Agent
# -----------------------------
def validation_agent(state: VCycleState) -> VCycleState:
    prompt = f"""
Validate whether the generated tests fully cover the requirements.

Requirements:
{state['requirement_output']}

Tests:
{state['test_output']}

Return:
1. Coverage analysis
2. Missing test cases
3. Risk assessment
4. Validation verdict
"""

    output = ask_llm(
        system_prompt="You are a software validation expert.",
        user_prompt=prompt,
    )

    state["validation_output"] = output
    append_history(state, "validation_agent", output)

    review = human_loop("Validation Agent", output)

    state["approved"] = review["approved"]
    state["human_feedback"] = review["feedback"]

    return state


# -----------------------------
# Final Q&A Agent
# -----------------------------
def qa_agent(state: VCycleState) -> VCycleState:
    prompt = f"""
Create a final project Q&A summary.

Requirements:
{state['requirement_output']}

Tests:
{state['test_output']}

Validation:
{state['validation_output']}

Generate:
1. Final summary
2. Known risks
3. Deployment checklist
4. Stakeholder Q&A
"""

    output = ask_llm(
        system_prompt="You are a final release governance expert.",
        user_prompt=prompt,
    )

    state["qa_output"] = output
    append_history(state, "qa_agent", output)

    review = human_loop("Final Q&A Agent", output)

    state["approved"] = review["approved"]
    state["human_feedback"] = review["feedback"]

    return state


# -----------------------------
# Routing logic
# -----------------------------
def requirement_router(state: VCycleState):
    if state["approved"]:
        return "test_agent"
    return "requirement_agent"


def test_router(state: VCycleState):
    if state["approved"]:
        return "validation_agent"
    return "test_agent"


def validation_router(state: VCycleState):
    if state["approved"]:
        return "qa_agent"
    return "validation_agent"


def qa_router(state: VCycleState):
    if state["approved"]:
        return END
    return "qa_agent"


# -----------------------------
# Build graph
# -----------------------------
graph = StateGraph(VCycleState)

graph.add_node("requirement_agent", requirement_agent)
graph.add_node("test_agent", test_agent)
graph.add_node("validation_agent", validation_agent)
graph.add_node("qa_agent", qa_agent)

graph.set_entry_point("requirement_agent")

graph.add_conditional_edges(
    "requirement_agent",
    requirement_router,
)

graph.add_conditional_edges(
    "test_agent",
    test_router,
)

graph.add_conditional_edges(
    "validation_agent",
    validation_router,
)

graph.add_conditional_edges(
    "qa_agent",
    qa_router,
)

app = graph.compile()


# -----------------------------
# Session persistence
# -----------------------------
def save_session(state: VCycleState):
    filename = f"session_{state['session_id']}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"\nSession saved to: {filename}")


# -----------------------------
# Main execution
# -----------------------------
if __name__ == "__main__":
    user_requirement = input("Enter project requirement: ").strip()

    initial_state: VCycleState = {
        "requirement": user_requirement,
        "requirement_output": "",
        "test_output": "",
        "validation_output": "",
        "qa_output": "",
        "human_feedback": "",
        "approved": False,
        "session_id": str(uuid.uuid4()),
        "history": [],
    }

    final_state = app.invoke(initial_state)

    save_session(final_state)

    print("\n" + "=" * 80)
    print("FINAL Q&A OUTPUT")
    print("=" * 80)
    print(final_state["qa_output"])