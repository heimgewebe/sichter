import express from "express";
import { MCPServer, Tool } from "@modelcontextprotocol/sdk";

const app = express();
app.use(express.json());

const tools = {

  pr_review: new Tool({
    description: "Analyse a PR using sichter logic",
    parameters: {
      type: "object",
      properties: {
        repo: { type: "string" },
        number: { type: "number" }
      },
      required: ["repo", "number"]
    },
    execute: async ({ repo, number }) => {

      // später ersetzt durch echte sichter-Logik
      return {
        summary: `Sichter would analyze PR #${number} in ${repo}`,
        status: "mock"
      };
    }
  }),

  oversized_check: new Tool({
    description: "Check for oversized files using sichter rules",
    execute: async () => {
      return { result: "no oversized files found (mock)" };
    }
  })
};

const mcpServer = new MCPServer({ tools });

app.post("/v0.1/execute", async (req, res) => {
  const response = await mcpServer.handleExecute(req.body);
  res.json(response);
});

app.get("/v0.1/servers", (req, res) => {
  res.json({
    servers: {
      "heimgewebe-sichter": {
        tools: Object.keys(tools),
        type: "http",
        url: "https://your-sichter-deployment-url/api/mcp"
      }
    }
  });
});

app.listen(3000, () => {
  console.log("Sichter MCP server running on port 3000");
});
