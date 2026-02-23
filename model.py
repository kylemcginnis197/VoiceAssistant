import anthropic
import inspect
import json

from log import get_logger

log = get_logger("model")

def get_pydantic_parameters(tool: object):
    """Returns the first parameter's annotation if the tool has parameters, else None."""
    sig = inspect.signature(obj=tool)

    if len(sig.parameters) == 0:
        return None

    sig_iter = sig.parameters.items().__iter__()
    _, parameters = next(sig_iter)
    return parameters

def generate_declarations(tools: list[object]) -> list[dict]:
    """Auto-generate Anthropic tool declarations from tool functions."""
    res = []

    for tool in tools:
        name = tool.__name__

        if not name:
            raise RuntimeError("Failed to get function name during declaration generation.")

        tool_declaration = {
            "name": tool.__name__
        }

        if description := tool.__doc__:
            tool_declaration["description"] = description

        if parameter := get_pydantic_parameters(tool):
            tool_schema = parameter.annotation.model_json_schema()

            if tool_schema:
                tool_declaration["input_schema"] = {
                    "type": "object",
                    "properties": tool_schema.get("properties", {}),
                    "required": tool_schema.get("required", []),
                }

        res.append(tool_declaration)

    return res

class Model:
    def __init__(self, tools: list[object], web_search: bool = True) -> None:
        self.client = anthropic.Client()
        self.input_token_limit = 75_000
        self.output_token_limit = 4_096
        self.anthropic_model = "claude-sonnet-4-6-20250929"

        self.context_window = []

        self.tool_references = tools
        self.tools = generate_declarations(tools)

        try:
            with open(file="prompts/system_prompt.md", mode="r") as file:
                contents = file.read()
                self.system_prompt = contents
        except Exception as e:
            log.error(f"Failed to load system prompt: {e}")
            self.system_prompt = None

        if web_search:
            self.tools.append({
                "type": "web_search_20260209",
                "name": "web_search",
                "user_location": {
                    "type": "approximate",
                    "city": "Omaha",
                    "region": "Nebraska",
                    "country": "US",
                    "timezone": "America/Chicago"
                }
            })

    def clear_context_window(self):
        self.context_window = []

    def set_input_tokens(self, tokens):
        self.input_token_limit = tokens

    def set_output_tokens(self, tokens):
        self.output_token_limit = tokens

    def set_model(self, model_name: str) -> None:
        model_name = model_name.lower().strip()

        if model_name == "opus 4.6":
            self.anthropic_model = "claude-opus-4-6"
        elif model_name == "sonnet 4.6":
            self.anthropic_model = "claude-sonnet-4-6"
        elif model_name == "sonnet 4.5":
            self.anthropic_model = "claude-sonnet-4-5-20250929"
        else:
            self.anthropic_model = "claude-sonnet-4-6"

    async def execute_tool(self, tool_name, tool_args):
        for tool in self.tool_references:
            if tool.__name__ == tool_name:
                parameter = get_pydantic_parameters(tool)

                log.info(f"Tool call: {tool.__name__} with args: {tool_args}")

                try:
                    if parameter and parameter.annotation is not inspect.Parameter.empty:
                        pydantic_class = parameter.annotation
                        response = await tool(pydantic_class(**tool_args)) if inspect.iscoroutinefunction(tool) else tool(pydantic_class(**tool_args))
                    else:
                        response = await tool() if inspect.iscoroutinefunction(tool) else tool()
                except Exception as e:
                    return {
                        "status": "error",
                        "response": f"Failed to run {tool_name} with args: {tool_args}, error: {e}"
                    }
                else:
                    # print(f"tool response: {response}")

                    return {
                        "status": "success",
                        "response": response
                    }
        return {
            "status": "error",
            "response": f"Failed to find tool. No tool named {tool_name} with args: {tool_args}"
        }

    async def call_model(self, input: str) -> str:
        self.context_window.append({
            "role": "user",
            "content": input
        })

        while True:
            # print(f"context window: {self.context_window}")

            with self.client.beta.messages.stream(
                betas=["compact-2026-01-12"],
                model=self.anthropic_model,
                max_tokens=self.output_token_limit,
                system=self.system_prompt,
                thinking={"type": "adaptive"},
                tools=self.tools,
                messages=self.context_window,
                context_management={
                    "edits": [{
                        "type": "compact_20260112",
                        "trigger": {"type": "input_tokens", "value": self.input_token_limit},
                        "pause_after_compaction": True,
                        "instructions": "Focus on preserving big picture ideas and themes and tool call responses"
                    }]
                }
            ) as stream:
                response = stream.get_final_message()

            stop_reason = response.stop_reason
            content = response.content

            if stop_reason == "end_turn" or stop_reason == "max_tokens":
                output = ""

                for block in content:
                    if block.type == "text":
                        output += block.text

                return output
            elif stop_reason == "tool_use":
                self.context_window.append({"role": "assistant", "content": content})

                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        res = await self.execute_tool(tool_name=block.name, tool_args=block.input)

                        if res is None or not len(res):
                            res = "tool ran successfully."

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(res)
                        })

                self.context_window.append({
                    "role": "user",
                    "content": tool_results
                })
            elif stop_reason == "compaction":
                compacted_block = content[0]
                preserved_messages = self.context_window[-4:] if len(self.context_window) > 4 else self.context_window
                self.context_window = [compacted_block] + preserved_messages
            elif stop_reason == "pause_turn":
                self.context_window.extend([
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "Please continue."}
                ])
            elif stop_reason == "refusal":
                return "I'm not answering that shit."
