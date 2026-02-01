"""
test_agent.py - Simulates a Codex Agent talking to Tracé

This script acts as a "Mock Codex" to verify the MCP server works correctly.
It connects via STDIO and calls the exposed tools.
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_mock_codex():
    """Simulate an AI agent using Tracé as an MCP server."""
    
    # 1. Configure the connection to the Tracé MCP server
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "trace", "serve"],
        env=None
    )

    print("🤖 Mock Codex: Connecting to Tracé MCP Server...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 2. Initialize the session
            await session.initialize()
            print("✅ Connected to Tracé MCP Server", file=sys.stderr)
            
            # 3. List available tools
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"\n📋 Available Tools:", file=sys.stderr)
            for name in tool_names:
                print(f"   • {name}", file=sys.stderr)
            
            # Verify expected tools are present
            expected_tools = [
                "trace.run_and_capture",
                "trace.get_recent_evidence", 
                "trace.generate_report"
            ]
            for tool in expected_tools:
                if tool not in tool_names:
                    print(f"❌ Missing expected tool: {tool}", file=sys.stderr)
                    return False
            
            print("\n" + "=" * 60, file=sys.stderr)
            
            # 4. Scenario: Agent decides to run a command
            print("\n🤖 Mock Codex: I will now run 'echo Hello from Tracé MCP!' to gather evidence...", file=sys.stderr)
            
            result = await session.call_tool(
                "trace.run_and_capture",
                arguments={"command": "echo 'Hello from Tracé MCP Server!'"}
            )
            
            # Parse the JSON response
            tool_output = json.loads(result.content[0].text)
            
            if "error" in tool_output:
                print(f"❌ Error: {tool_output['error']}", file=sys.stderr)
                return False
            
            print(f"\n✅ Evidence Captured!", file=sys.stderr)
            print(f"   Session ID: {tool_output['session_id']}", file=sys.stderr)
            print(f"   Exit Code: {tool_output['exit_code']}", file=sys.stderr)
            print(f"   Duration: {tool_output['duration_ms']}ms", file=sys.stderr)
            print(f"   Evidence Path: {tool_output['evidence_path']}", file=sys.stderr)
            
            print("\n" + "=" * 60, file=sys.stderr)
            
            # 5. Scenario: Agent lists recent evidence
            print("\n🤖 Mock Codex: Checking recent evidence sessions...", file=sys.stderr)
            
            evidence_result = await session.call_tool(
                "trace.get_recent_evidence",
                arguments={"limit": 5}
            )
            
            evidence_list = json.loads(evidence_result.content[0].text)
            print(f"\n📦 Recent Evidence Sessions: {len(evidence_list)}", file=sys.stderr)
            for e in evidence_list[:3]:
                print(f"   • {e['session_id']}: {e['command'][:40]}...", file=sys.stderr)
            
            print("\n" + "=" * 60, file=sys.stderr)
            
            # 6. Scenario: Agent generates a report
            print("\n🤖 Mock Codex: Generating HTML report...", file=sys.stderr)
            
            report_result = await session.call_tool(
                "trace.generate_report",
                arguments={"open_browser": False}
            )
            
            report_output = json.loads(report_result.content[0].text)
            
            if "error" in report_output:
                print(f"⚠️ Report generation: {report_output['error']}", file=sys.stderr)
            else:
                print(f"\n🎉 Report Generated!", file=sys.stderr)
                print(f"   File: {report_output['file_path']}", file=sys.stderr)
                print(f"   Evidence Count: {report_output['evidence_count']}", file=sys.stderr)
            
            print("\n" + "=" * 60, file=sys.stderr)
            print("✅ All MCP tests passed!", file=sys.stderr)
            return True


if __name__ == "__main__":
    print("\n" + "=" * 60, file=sys.stderr)
    print("   TRACÉ MCP SERVER - MOCK CODEX TEST", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)
    
    try:
        success = asyncio.run(run_mock_codex())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
