import express from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const app = express();
app.use(express.json());

const server = new McpServer({
  name: "heimgewebe-sichter",
  version: "0.1.0"
});

// PR Review Tool (Mock)
server.tool(
  "pr_review",
  {
    repo: z.string(),
    number: z.number()
  },
  async ({ repo, number }) => {
    return {
      summary: `Sichter review (mock) for ${repo}#${number}`,
      severity: "info",
      findings: [
        {
          title: "Mock check only",
          path: "",
          details: "Replace this with real sichter analysis."
        }
      ]
    };
  }
);

// MCP über stdio startbar
server.start(new StdioServerTransport());

// HTTP-Expose für spätere Registry-Abfragen
app.post("/v0.1/execute", async (req, res) => {
  const response = await server.handleExecute(req.body);
  res.json(response);
});

app.get("/v0.1/servers", (_req, res) => {
  res.json({
    servers: {
      "heimgewebe-sichter": {
        tools: ["pr_review"],
        type: "http",
        url: "http://localhost:3000"
      }
    }
  });
});

app.listen(3000, () => {
  console.log("Sichter MCP server running on port 3000");
});
