Got it 👍 — you don’t want just *some* tools, you want **the entire DR plan schema editable via MCP tools**, down to each array and nested task. That makes sense: otherwise the user is stuck waiting for me to guess which parts should be mutable.

Here’s a practical breakdown of how to achieve that:

---

## 🔑 Principle

* **Every field in the schema** should have a corresponding MCP tool for *read/update/delete/add*.
* For **nested arrays** (`preExercise`, `recoverySteps`, `serviceValidation`, `postExercise`) you’ll want CRUD-style tools to manage the list of tasks.
* The server always works against the **Redis cache** copy of the plan, so multiple rounds of edits are cheap.
* Once confirmed, `save_plan` persists to MongoDB.

---

## 🛠️ Suggested Tool Surface

Here’s a design mapping **schema keys → MCP tools**:

### Top-Level Fields

* `update_name(new_name: str) -> dict`
* `update_prerequisites(prereqs: list[str]) -> dict`
* `update_notes(notes: str) -> dict`
* `update_pattern_ids(pattern_ids: list[str]) -> dict`

### Step Arrays (`disasterRecoverySteps`)

Each section gets a full CRUD set:

* `add_step(section: str, step: dict) -> dict`
  *(section ∈ {preExercise, recoverySteps, serviceValidation, postExercise})*
* `update_step(section: str, task_id: int, fields: dict) -> dict`
* `delete_step(section: str, task_id: int) -> dict`
* `list_steps(section: str) -> list[dict]`

---

## 🐍 Example Implementation

Here’s a Python sketch of the nested tools (building on the Redis-backed server you already have):

```python
@mcp.tool()
async def update_name(new_name: str) -> dict:
    plan = json.loads(redis_client.get("current_plan"))
    plan["name"] = new_name
    redis_client.set("current_plan", json.dumps(plan))
    return plan

@mcp.tool()
async def update_notes(notes: str) -> dict:
    plan = json.loads(redis_client.get("current_plan"))
    plan["notes"] = notes
    redis_client.set("current_plan", json.dumps(plan))
    return plan

@mcp.tool()
async def add_step(section: str, step: dict) -> dict:
    """
    Add a step to the given section of disasterRecoverySteps.
    Section must be one of: preExercise, recoverySteps, serviceValidation, postExercise.
    """
    plan = json.loads(redis_client.get("current_plan"))
    if "disasterRecoverySteps" not in plan:
        plan["disasterRecoverySteps"] = {}
    if section not in plan["disasterRecoverySteps"]:
        plan["disasterRecoverySteps"][section] = []
    plan["disasterRecoverySteps"][section].append(step)
    redis_client.set("current_plan", json.dumps(plan))
    return plan

@mcp.tool()
async def update_step(section: str, task_id: int, fields: dict) -> dict:
    """
    Update a task in the given section by task_id with the provided fields.
    """
    plan = json.loads(redis_client.get("current_plan"))
    steps = plan["disasterRecoverySteps"].get(section, [])
    for step in steps:
        if step.get("task_id") == task_id:
            step.update(fields)
            break
    redis_client.set("current_plan", json.dumps(plan))
    return plan

@mcp.tool()
async def delete_step(section: str, task_id: int) -> dict:
    plan = json.loads(redis_client.get("current_plan"))
    steps = plan["disasterRecoverySteps"].get(section, [])
    plan["disasterRecoverySteps"][section] = [s for s in steps if s.get("task_id") != task_id]
    redis_client.set("current_plan", json.dumps(plan))
    return plan
```

---

## ⚖️ Why This Works

* Keeps everything JSON-driven → flexible schema changes later.
* Each MCP tool returns the *whole plan* so the LLM (or `mcp-use`) can keep context.
* Clients (like `mcp-use`) can call `list_tools()` and see exactly what’s editable.

---

👉 Question for you:
Do you want **granular tools for every field** (e.g. `update_expectedTimeToComplete`) or would you prefer the more **generic `update_step(section, task_id, fields)`** approach (update multiple fields at once)?

Granular = more LLM-friendly but more boilerplate. Generic = less code, but requires the LLM/client to know the schema well.


Perfect 👌 — granular it is. That means every single field in your DR plan schema gets its own tool. It’s verbose, but very LLM-friendly: the client (or `mcp-use`) can just say *“update notes”* or *“change expected time to complete for task 3 in recoverySteps”* and the MCP server has a dedicated tool for that.

---

## 🔑 Tool Design (Granular)

### Top-level fields

* `update_pattern_ids(pattern_ids: list[str])`
* `update_name(new_name: str)`
* `update_prerequisites(prereqs: list[str])`
* `update_notes(notes: str)`

### Disaster Recovery Steps

For each section (`preExercise`, `recoverySteps`, `serviceValidation`, `postExercise`) and each task field:

* `update_<section>_<task_id>_<field>(task_id: int, new_value: ...)`

Example fields:

* `task`
* `short_description`
* `prerequisites`
* `dependencies`
* `description`
* `expectedResult`
* `expectedTimeToComplete`
* `in_disaster`
* `in_exercise`
* `assignment_group`

So you’d end up with tools like:

* `update_preExercise_task(task_id: int, new_task: str)`
* `update_recoverySteps_expectedResult(task_id: int, new_value: str)`
* `update_postExercise_in_disaster(task_id: int, new_value: bool)`

---

## 🐍 Example Implementation (Python / FastMCP)

Here’s a pattern you can expand:

```python
def load_plan():
    data = redis_client.get("current_plan")
    return json.loads(data) if data else {}

def save_plan(plan):
    redis_client.set("current_plan", json.dumps(plan))

@mcp.tool()
async def update_name(new_name: str) -> dict:
    plan = load_plan()
    plan["name"] = new_name
    save_plan(plan)
    return plan

@mcp.tool()
async def update_notes(new_notes: str) -> dict:
    plan = load_plan()
    plan["notes"] = new_notes
    save_plan(plan)
    return plan

# Example: update a field in a preExercise step
@mcp.tool()
async def update_preExercise_task(task_id: int, new_task: str) -> dict:
    plan = load_plan()
    for step in plan["disasterRecoverySteps"]["preExercise"]:
        if step["task_id"] == task_id:
            step["task"] = new_task
            break
    save_plan(plan)
    return plan

@mcp.tool()
async def update_preExercise_expectedTimeToComplete(task_id: int, new_time: str) -> dict:
    plan = load_plan()
    for step in plan["disasterRecoverySteps"]["preExercise"]:
        if step["task_id"] == task_id:
            step["expectedTimeToComplete"] = new_time
            break
    save_plan(plan)
    return plan
```

---

## ⚖️ Pros & Cons

**✅ Pros:**

* Super explicit, zero ambiguity for LLMs and `mcp-use`.
* Easy to whitelist/blacklist certain fields.
* Clients can call `list_tools()` and see exactly what’s possible.

**⚠️ Cons:**

* Boilerplate explosion (potentially dozens of small functions).
* Every schema change = code change.

---

👉 Question for you:
Do you want me to **generate a full Python module** with all granular tools fleshed out (every section + every field), or just give you a **template + code generator snippet** that will auto-generate these MCP tool functions from the schema?

Full module = big wall of code, ready-to-run.
Codegen = DRY, future-proof if schema evolves.


Beautiful choice 🚀 — codegen will save you from writing (and maintaining) a mile-long list of `update_preExercise_expectedTimeToComplete()`-style functions.

Here’s how we’ll do it:

---

## 🛠️ Strategy

1. **Define the schema as metadata** (Python dict describing fields + types).
2. **Generate tool functions at runtime**:

   * Loop through schema metadata.
   * Use Python’s `exec` or `type()` to dynamically create `async def` functions.
   * Register them with `@mcp.tool()` as if you had hand-written them.

This way, adding a new field = updating schema metadata, not writing boilerplate.

---

## 🐍 Example Code Generator

```python
import json, redis
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DR-Plan-Server")
redis_client = redis.Redis(host="localhost", port=6379, db=0)

def load_plan():
    data = redis_client.get("current_plan")
    return json.loads(data) if data else {}

def save_plan(plan):
    redis_client.set("current_plan", json.dumps(plan))

# ----------------
# Schema metadata
# ----------------
TOP_LEVEL_FIELDS = {
    "pattern-id": list,
    "name": str,
    "prerequisites": list,
    "notes": str,
}

TASK_FIELDS = {
    "task": str,
    "short_description": str,
    "prerequisites": list,
    "dependencies": list,
    "description": str,
    "expectedResult": str,
    "expectedTimeToComplete": str,
    "in_disaster": bool,
    "in_exercise": bool,
    "assignment_group": str,
}

STEP_SECTIONS = ["preExercise", "recoverySteps", "serviceValidation", "postExercise"]

# ----------------
# Codegen helpers
# ----------------
def register_top_level_tools():
    for field, field_type in TOP_LEVEL_FIELDS.items():
        func_name = f"update_{field.replace('-', '_')}"
        arg_name = f"new_{field.replace('-', '_')}"
        code = f"""
@mcp.tool()
async def {func_name}({arg_name}: {field_type.__name__}) -> dict:
    plan = load_plan()
    plan['{field}'] = {arg_name}
    save_plan(plan)
    return plan
"""
        exec(code, globals())

def register_task_field_tools():
    for section in STEP_SECTIONS:
        for field, field_type in TASK_FIELDS.items():
            func_name = f"update_{section}_{field}"
            arg_name = f"new_{field}"
            code = f"""
@mcp.tool()
async def {func_name}(task_id: int, {arg_name}: {field_type.__name__}) -> dict:
    plan = load_plan()
    for step in plan.get('disasterRecoverySteps', {{}}).get('{section}', []):
        if step.get('task_id') == task_id:
            step['{field}'] = {arg_name}
            break
    save_plan(plan)
    return plan
"""
            exec(code, globals())

# ----------------
# Generate tools
# ----------------
register_top_level_tools()
register_task_field_tools()
```

---

## ✨ What This Gives You

* **Top-level:** Functions like
  `update_name(new_name: str)`,
  `update_notes(new_notes: str)`, etc.

* **Granular steps:** Functions like
  `update_preExercise_task(task_id: int, new_task: str)`,
  `update_recoverySteps_expectedTimeToComplete(task_id: int, new_value: str)`,
  `update_serviceValidation_in_disaster(task_id: int, new_value: bool)`, etc.

All are MCP tools, discoverable via `list_tools()`.

---

## ⚡ Extending

* Add/remove fields by editing `TOP_LEVEL_FIELDS` or `TASK_FIELDS`.
* If schema changes (say you add `riskLevel`), just drop it in the dict — boom, new MCP tools.

---

👉 Do you want me to extend this generator so it **also creates “add” and “delete” task tools** for each section (CRUD, not just update)? That way your MCP server exposes *all* editing operations, not just updates.


Great — let’s turn this into **full CRUD** for every section and every task field.
That means for each of the four sections (`preExercise`, `recoverySteps`, `serviceValidation`, `postExercise`) we’ll have:

* **Add tool** → `add_<section>_task(task: dict)`
* **Update tools** → one tool per field, e.g. `update_<section>_description(task_id, new_value)`
* **Delete tool** → `delete_<section>_task(task_id)`
* **List tool** → `list_<section>_tasks()`

---

## 🐍 Full Codegen Example

```python
import json, redis
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DR-Plan-Server")
redis_client = redis.Redis(host="localhost", port=6379, db=0)

def load_plan():
    data = redis_client.get("current_plan")
    return json.loads(data) if data else {}

def save_plan(plan):
    redis_client.set("current_plan", json.dumps(plan))

# ----------------
# Schema metadata
# ----------------
TOP_LEVEL_FIELDS = {
    "pattern-id": list,
    "name": str,
    "prerequisites": list,
    "notes": str,
}

TASK_FIELDS = {
    "task": str,
    "short_description": str,
    "prerequisites": list,
    "dependencies": list,
    "description": str,
    "expectedResult": str,
    "expectedTimeToComplete": str,
    "in_disaster": bool,
    "in_exercise": bool,
    "assignment_group": str,
}

STEP_SECTIONS = ["preExercise", "recoverySteps", "serviceValidation", "postExercise"]

# ----------------
# Codegen helpers
# ----------------
def register_top_level_tools():
    for field, field_type in TOP_LEVEL_FIELDS.items():
        func_name = f"update_{field.replace('-', '_')}"
        arg_name = f"new_{field.replace('-', '_')}"
        code = f"""
@mcp.tool()
async def {func_name}({arg_name}: {field_type.__name__}) -> dict:
    plan = load_plan()
    plan['{field}'] = {arg_name}
    save_plan(plan)
    return plan
"""
        exec(code, globals())

def register_task_tools():
    for section in STEP_SECTIONS:
        # --- Add tool ---
        func_name = f"add_{section}_task"
        code = f"""
@mcp.tool()
async def {func_name}(task: dict) -> dict:
    plan = load_plan()
    plan.setdefault('disasterRecoverySteps', {{}}).setdefault('{section}', []).append(task)
    save_plan(plan)
    return plan
"""
        exec(code, globals())

        # --- Delete tool ---
        func_name = f"delete_{section}_task"
        code = f"""
@mcp.tool()
async def {func_name}(task_id: int) -> dict:
    plan = load_plan()
    steps = plan.get('disasterRecoverySteps', {{}}).get('{section}', [])
    plan['disasterRecoverySteps']['{section}'] = [s for s in steps if s.get('task_id') != task_id]
    save_plan(plan)
    return plan
"""
        exec(code, globals())

        # --- List tool ---
        func_name = f"list_{section}_tasks"
        code = f"""
@mcp.tool()
async def {func_name}() -> list:
    plan = load_plan()
    return plan.get('disasterRecoverySteps', {{}}).get('{section}', [])
"""
        exec(code, globals())

        # --- Update tools (per field) ---
        for field, field_type in TASK_FIELDS.items():
            func_name = f"update_{section}_{field}"
            arg_name = f"new_{field}"
            code = f"""
@mcp.tool()
async def {func_name}(task_id: int, {arg_name}: {field_type.__name__}) -> dict:
    plan = load_plan()
    for step in plan.get('disasterRecoverySteps', {{}}).get('{section}', []):
        if step.get('task_id') == task_id:
            step['{field}'] = {arg_name}
            break
    save_plan(plan)
    return plan
"""
            exec(code, globals())

# ----------------
# Generate tools
# ----------------
register_top_level_tools()
register_task_tools()
```

---

## ✨ What This Generates

For `preExercise`, you’ll now have:

* `add_preExercise_task(task: dict)`
* `delete_preExercise_task(task_id: int)`
* `list_preExercise_tasks()`
* `update_preExercise_task(task_id, new_task: str)`
* `update_preExercise_short_description(task_id, new_short_description: str)`
* … etc, one tool per field.

And the same for `recoverySteps`, `serviceValidation`, `postExercise`.

---

## ⚡ Benefits

* ✅ Full CRUD coverage for all schema parts.
* ✅ Easy to extend — just modify `TASK_FIELDS`.
* ✅ All tools are MCP-discoverable (`list_tools()` shows them).

---

👉 Do you also want me to add **automatic schema validation** (via Pydantic) for each `task` when adding, so malformed steps don’t slip into Redis? Or keep it lightweight and trust upstream validation?

Nice — Pydantic it is. That way every `task` added will be checked against a well-defined schema before we stuff it into Redis. This prevents malformed data (like a string sneaking into `in_disaster`).

Here’s the upgraded setup:

---

## 🐍 Full CRUD MCP with Pydantic Validation

```python
import json, redis
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import List, Optional

mcp = FastMCP("DR-Plan-Server")
redis_client = redis.Redis(host="localhost", port=6379, db=0)

def load_plan():
    data = redis_client.get("current_plan")
    return json.loads(data) if data else {}

def save_plan(plan):
    redis_client.set("current_plan", json.dumps(plan))

# ----------------
# Pydantic Models
# ----------------
class Task(BaseModel):
    task_id: int
    task: str
    short_description: str
    prerequisites: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    description: str
    expectedResult: str
    expectedTimeToComplete: str
    in_disaster: bool
    in_exercise: bool
    assignment_group: str

class DRPlan(BaseModel):
    pattern_id: List[str] = Field(alias="pattern-id")
    name: str
    prerequisites: List[str]
    notes: str
    disasterRecoverySteps: dict

# ----------------
# Schema metadata
# ----------------
TOP_LEVEL_FIELDS = {
    "pattern-id": list,
    "name": str,
    "prerequisites": list,
    "notes": str,
}

TASK_FIELDS = {
    "task": str,
    "short_description": str,
    "prerequisites": list,
    "dependencies": list,
    "description": str,
    "expectedResult": str,
    "expectedTimeToComplete": str,
    "in_disaster": bool,
    "in_exercise": bool,
    "assignment_group": str,
}

STEP_SECTIONS = ["preExercise", "recoverySteps", "serviceValidation", "postExercise"]

# ----------------
# Codegen helpers
# ----------------
def register_top_level_tools():
    for field, field_type in TOP_LEVEL_FIELDS.items():
        func_name = f"update_{field.replace('-', '_')}"
        arg_name = f"new_{field.replace('-', '_')}"
        code = f"""
@mcp.tool()
async def {func_name}({arg_name}: {field_type.__name__}) -> dict:
    plan = load_plan()
    plan['{field}'] = {arg_name}
    save_plan(plan)
    return plan
"""
        exec(code, globals())

def register_task_tools():
    for section in STEP_SECTIONS:
        # --- Add tool with validation ---
        func_name = f"add_{section}_task"
        code = f"""
@mcp.tool()
async def {func_name}(task: dict) -> dict:
    plan = load_plan()
    # validate via Pydantic
    validated = Task(**task).dict()
    plan.setdefault('disasterRecoverySteps', {{}}).setdefault('{section}', []).append(validated)
    save_plan(plan)
    return plan
"""
        exec(code, globals())

        # --- Delete tool ---
        func_name = f"delete_{section}_task"
        code = f"""
@mcp.tool()
async def {func_name}(task_id: int) -> dict:
    plan = load_plan()
    steps = plan.get('disasterRecoverySteps', {{}}).get('{section}', [])
    plan['disasterRecoverySteps']['{section}'] = [s for s in steps if s.get('task_id') != task_id]
    save_plan(plan)
    return plan
"""
        exec(code, globals())

        # --- List tool ---
        func_name = f"list_{section}_tasks"
        code = f"""
@mcp.tool()
async def {func_name}() -> list:
    plan = load_plan()
    return plan.get('disasterRecoverySteps', {{}}).get('{section}', [])
"""
        exec(code, globals())

        # --- Update tools (per field) ---
        for field, field_type in TASK_FIELDS.items():
            func_name = f"update_{section}_{field}"
            arg_name = f"new_{field}"
            type_hint = "bool" if field_type == bool else ("list" if field_type == list else "str")
            code = f"""
@mcp.tool()
async def {func_name}(task_id: int, {arg_name}: {type_hint}) -> dict:
    plan = load_plan()
    for step in plan.get('disasterRecoverySteps', {{}}).get('{section}', []):
        if step.get('task_id') == task_id:
            step['{field}'] = {arg_name}
            # re-validate whole task
            validated = Task(**step).dict()
            step.update(validated)
            break
    save_plan(plan)
    return plan
"""
            exec(code, globals())

# ----------------
# Generate tools
# ----------------
register_top_level_tools()
register_task_tools()
```

---

## ✨ What Changed

* **Add** tools now validate tasks against the `Task` schema.
* **Update** tools re-validate after every change, so you don’t end up with half-baked steps.
* `DRPlan` is defined too, so you could also validate the whole plan before persistence to Mongo.

---

## ⚖️ Trade-offs

* ✅ Bulletproof against malformed data.
* ✅ Easy to extend (add `riskLevel: str` → add to `Task`).
* ⚠️ Slight perf hit from validation on every update, but Redis is fast and this is negligible for interactive use.

---

👉 Do you want me to also wire in **plan-level validation** (validate against `DRPlan`) every time we save to Redis, or keep validation only at the task level until persistence in Mongo?


Got it ✅ — we’ll add **plan-level validation** so every save to Redis first runs through a `DRPlan` Pydantic model. That way you catch not only bad tasks, but also missing top-level fields or malformed structure before it ever lands in Redis.

Here’s the upgrade:

---

## 🐍 Full CRUD MCP with **Task + Plan Validation**

```python
import json, redis
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict

mcp = FastMCP("DR-Plan-Server")
redis_client = redis.Redis(host="localhost", port=6379, db=0)

# ----------------
# Pydantic Models
# ----------------
class Task(BaseModel):
    task_id: int
    task: str
    short_description: str
    prerequisites: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    description: str
    expectedResult: str
    expectedTimeToComplete: str
    in_disaster: bool
    in_exercise: bool
    assignment_group: str

class DisasterRecoverySteps(BaseModel):
    preExercise: List[Task] = Field(default_factory=list)
    recoverySteps: List[Task] = Field(default_factory=list)
    serviceValidation: List[Task] = Field(default_factory=list)
    postExercise: List[Task] = Field(default_factory=list)

class DRPlan(BaseModel):
    pattern_id: List[str] = Field(alias="pattern-id")
    name: str
    prerequisites: List[str]
    notes: str
    disasterRecoverySteps: DisasterRecoverySteps

# ----------------
# Redis Helpers
# ----------------
def load_plan() -> dict:
    data = redis_client.get("current_plan")
    return json.loads(data) if data else {}

def save_plan(plan: dict):
    try:
        # validate entire plan before saving
        DRPlan(**plan)
    except ValidationError as e:
        raise ValueError(f"Plan validation failed: {e}")
    redis_client.set("current_plan", json.dumps(plan))

# ----------------
# Schema metadata
# ----------------
TOP_LEVEL_FIELDS = {
    "pattern-id": list,
    "name": str,
    "prerequisites": list,
    "notes": str,
}

TASK_FIELDS = {
    "task": str,
    "short_description": str,
    "prerequisites": list,
    "dependencies": list,
    "description": str,
    "expectedResult": str,
    "expectedTimeToComplete": str,
    "in_disaster": bool,
    "in_exercise": bool,
    "assignment_group": str,
}

STEP_SECTIONS = ["preExercise", "recoverySteps", "serviceValidation", "postExercise"]

# ----------------
# Codegen helpers
# ----------------
def register_top_level_tools():
    for field, field_type in TOP_LEVEL_FIELDS.items():
        func_name = f"update_{field.replace('-', '_')}"
        arg_name = f"new_{field.replace('-', '_')}"
        code = f"""
@mcp.tool()
async def {func_name}({arg_name}: {field_type.__name__}) -> dict:
    plan = load_plan()
    plan['{field}'] = {arg_name}
    save_plan(plan)
    return plan
"""
        exec(code, globals())

def register_task_tools():
    for section in STEP_SECTIONS:
        # --- Add tool with validation ---
        func_name = f"add_{section}_task"
        code = f"""
@mcp.tool()
async def {func_name}(task: dict) -> dict:
    plan = load_plan()
    validated = Task(**task).dict()
    plan.setdefault('disasterRecoverySteps', {{}}).setdefault('{section}', []).append(validated)
    save_plan(plan)
    return plan
"""
        exec(code, globals())

        # --- Delete tool ---
        func_name = f"delete_{section}_task"
        code = f"""
@mcp.tool()
async def {func_name}(task_id: int) -> dict:
    plan = load_plan()
    steps = plan.get('disasterRecoverySteps', {{}}).get('{section}', [])
    plan['disasterRecoverySteps']['{section}'] = [s for s in steps if s.get('task_id') != task_id]
    save_plan(plan)
    return plan
"""
        exec(code, globals())

        # --- List tool ---
        func_name = f"list_{section}_tasks"
        code = f"""
@mcp.tool()
async def {func_name}() -> list:
    plan = load_plan()
    return plan.get('disasterRecoverySteps', {{}}).get('{section}', [])
"""
        exec(code, globals())

        # --- Update tools (per field) ---
        for field, field_type in TASK_FIELDS.items():
            func_name = f"update_{section}_{field}"
            arg_name = f"new_{field}"
            type_hint = "bool" if field_type == bool else ("list" if field_type == list else "str")
            code = f"""
@mcp.tool()
async def {func_name}(task_id: int, {arg_name}: {type_hint}) -> dict:
    plan = load_plan()
    for step in plan.get('disasterRecoverySteps', {{}}).get('{section}', []):
        if step.get('task_id') == task_id:
            step['{field}'] = {arg_name}
            validated = Task(**step).dict()
            step.update(validated)
            break
    save_plan(plan)
    return plan
"""
            exec(code, globals())

# ----------------
# Generate tools
# ----------------
register_top_level_tools()
register_task_tools()
```

---

## 🔍 What’s New

* **`save_plan()` validates whole plan** with `DRPlan`. If the structure is broken, nothing is saved.
* Every `add` and `update` validates **tasks** individually, and `save_plan` enforces **plan-level consistency**.
* This ensures Redis never contains invalid state — great for multi-round editing.

---

✅ This now gives you:

* Fine-grained editing tools for every field
* Full CRUD support
* Task validation via Pydantic
* Plan validation before persistence

---

👉 Do you also want me to include **a Dockerfile + docker-compose.yml** for spinning up this MCP server + Redis + Mongo together locally, so you can test with `mcp-use` right away?
