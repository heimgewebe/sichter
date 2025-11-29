import express from "express";
import { MCPServer, Tool } from "@modelcontextprotocol/sdk";
import { execSync } from "child_process";

const app = express();
app.use(express.json());

const tools = {

  pr_review: new Tool({
    description: "Run sichter review on a GitHub PR",
    parameters: {
      type: "object",
      properties: {
        repo: { type: "string", description: "owner/repo" },
        number: { type: "number", description: "Pull request number" }
      },
      required: ["repo", "number"]
    },
    execute: async ({ repo, number }) => {
      // hier später: echter sichter-Aufruf, z.B.:
      // const out = execSync(`./scripts/sichter_pr_review.sh ${repo} ${number}`, { encoding: "utf8" });

      // Für jetzt: Dummy mit klarer Struktur
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
  })
};

const mcpServer = new MCPServer({ tools });

// MCP execute endpoint
app.post("/v0.1/execute", async (req, res) => {
  const response = await mcpServer.handleExecute(req.body);
  res.json(response);
});

// Discovery endpoint (Registry-freundlich)
app.get("/v0.1/servers", (req, res) => {
  res.json({
    servers: {
      "heimgewebe-sichter": {
        tools: Object.keys(tools),
        type: "http",
        url: "http://localhost:3000/api/mcp"
      }
    }
  });
});

app.listen(3000, () => {
  console.log("Sichter MCP server running on port 3000");
});
