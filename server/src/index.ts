import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import OpenAI from "openai";
import { google } from "googleapis";

dotenv.config({ path: ".env", override: true });

const app = express();
const port = Number(process.env.PORT || 4000);

app.use(cors());
app.use(express.json({ limit: "2mb" }));

function decodeBase64Url(data: string): string {
  return Buffer.from(
    data.replace(/-/g, "+").replace(/_/g, "/"),
    "base64"
  ).toString("utf-8");
}

function getHeader(
  headers: Array<{ name?: string | null; value?: string | null }>,
  name: string
): string {
  return (
    headers.find(
      (header) => header.name?.toLowerCase() === name.toLowerCase()
    )?.value ?? ""
  );
}

function extractEmailBody(payload: any): string {
  if (!payload) return "";

  if (payload.mimeType === "text/plain" && payload.body?.data) {
    return decodeBase64Url(payload.body.data);
  }

  if (payload.parts) {
    for (const part of payload.parts) {
      const body = extractEmailBody(part);

      if (body.trim()) {
        return body;
      }
    }
  }

  if (payload.body?.data) {
    return decodeBase64Url(payload.body.data);
  }

  return "";
}

const googleOAuthClient = new google.auth.OAuth2(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET,
  process.env.GOOGLE_REDIRECT_URI
);

let gmailTokens: any = null;

const gmailScopes = [
  "https://www.googleapis.com/auth/gmail.readonly",
];

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || "missing-key",
});

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    app: "Inbox2Done API",
  });
});

app.post("/analyze-email", async (req, res) => {
  try {
    const { emailText } = req.body;

    if (!emailText || typeof emailText !== "string") {
      return res.status(400).json({
        error: "emailText is required",
      });
    }

    const completion = await openai.chat.completions.create({
      model: "gpt-4.1-mini",
      temperature: 0.2,
      messages: [
        {
          role: "system",
          content: `
You are Inbox2Done, an email productivity assistant.

Return only valid JSON with this shape:
{
  "summary": "string",
  "priority": "High | Medium | Low",
  "category": "billing | school | work | appointment | shopping | personal | spam | other",
  "recommendedActions": ["string"],
  "deadlines": ["string"],
  "suggestedReply": "string"
}

Do not invent facts or deadlines.
If no reply is needed, return an empty string.
          `.trim(),
        },
        {
          role: "user",
          content: emailText,
        },
      ],
    });

    const content = completion.choices[0]?.message?.content;

    if (!content) {
      return res.status(500).json({
        error: "No model response returned",
      });
    }

    const analysis = JSON.parse(content);

    return res.json(analysis);
  } catch (error) {
    console.error(error);

    return res.status(500).json({
      error: "Failed to analyze email",
    });
  }
});

app.get("/auth/google", (_req, res) => {
  const authUrl = googleOAuthClient.generateAuthUrl({
    access_type: "offline",
    prompt: "consent",
    scope: gmailScopes,
  });

  res.redirect(authUrl);
});

app.get("/auth/google/callback", async (req, res) => {
  try {
    const code = req.query.code;

    if (!code || typeof code !== "string") {
      return res.status(400).send("Missing authorization code");
    }

    const { tokens } = await googleOAuthClient.getToken(code);

    gmailTokens = tokens;
    googleOAuthClient.setCredentials(tokens);

    return res.send(`
      <h1>Gmail connected successfully</h1>
      <p>You can close this tab.</p>
    `);
  } catch (error) {
    console.error(error);
    return res.status(500).send("Failed to connect Gmail");
  }
});

app.get("/gmail/status", (_req, res) => {
  res.json({
    connected: Boolean(gmailTokens),
  });
});

app.get("/gmail/today", async (_req, res) => {
  try {
    if (!gmailTokens) {
      return res.status(401).json({
        error: "Gmail is not connected",
      });
    }

    googleOAuthClient.setCredentials(gmailTokens);

    const gmail = google.gmail({
      version: "v1",
      auth: googleOAuthClient,
    });

    const now = new Date();

    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");

    const today = `${year}/${month}/${day}`;

    const listResponse = await gmail.users.messages.list({
      userId: "me",
      q: `after:${today}`,
      maxResults: 50,
    });

    const messages = listResponse.data.messages ?? [];

    const emails = await Promise.all(
      messages.map(async ({ id }) => {
        if (!id) return null;

        const response = await gmail.users.messages.get({
          userId: "me",
          id,
          format: "full",
        });

        const message = response.data;
        const headers = message.payload?.headers ?? [];

        return {
          id: message.id,
          threadId: message.threadId,
          from: getHeader(headers, "From"),
          subject: getHeader(headers, "Subject"),
          date: getHeader(headers, "Date"),
          snippet: message.snippet ?? "",
          body: extractEmailBody(message.payload),
        };
      })
    );

    return res.json({
      count: emails.filter(Boolean).length,
      emails: emails.filter(Boolean),
    });
  } catch (error) {
    console.error("Failed to fetch today's Gmail:", error);

    return res.status(500).json({
      error: "Failed to fetch today's Gmail messages",
    });
  }
});

app.get("/gmail/daily-summary", async (_req, res) => {
  try {
    if (!gmailTokens) {
      return res.status(401).json({
        error: "Gmail is not connected",
      });
    }

    googleOAuthClient.setCredentials(gmailTokens);

    const gmail = google.gmail({
      version: "v1",
      auth: googleOAuthClient,
    });

    const now = new Date();
    const today = `${now.getFullYear()}/${String(
      now.getMonth() + 1
    ).padStart(2, "0")}/${String(now.getDate()).padStart(2, "0")}`;

    const listResponse = await gmail.users.messages.list({
      userId: "me",
      q: `after:${today}`,
      maxResults: 50,
    });

    const messages = listResponse.data.messages ?? [];

    if (messages.length === 0) {
      return res.json({
        overview: "No emails were received today.",
        urgentItems: [],
        recommendedActions: [],
        deadlines: [],
        emails: [],
      });
    }

    const emails = (
      await Promise.all(
        messages.map(async ({ id }) => {
          if (!id) return null;

          const response = await gmail.users.messages.get({
            userId: "me",
            id,
            format: "full",
          });

          const message = response.data;
          const headers = message.payload?.headers ?? [];

          return {
            from: getHeader(headers, "From"),
            subject: getHeader(headers, "Subject"),
            date: getHeader(headers, "Date"),
            body:
              extractEmailBody(message.payload).slice(0, 5000) ||
              message.snippet ||
              "",
          };
        })
      )
    ).filter(Boolean);

    const emailBatch = emails
      .map(
        (email, index) => `
EMAIL ${index + 1}
From: ${email?.from}
Subject: ${email?.subject}
Date: ${email?.date}
Body:
${email?.body}
`
      )
      .join("\n----------------------\n");

    const completion = await openai.chat.completions.create({
      model: "gpt-4.1-mini",
      temperature: 0.2,
      messages: [
        {
          role: "system",
          content: `
You are Inbox2Done, a daily email briefing assistant.

Analyze the user's emails from today.

Return only valid JSON with this exact shape:
{
  "overview": "A concise overview of today's inbox",
  "urgentItems": [
    {
      "subject": "Email subject",
      "reason": "Why it is urgent"
    }
  ],
  "recommendedActions": [
    {
      "action": "What the user should do",
      "relatedSubject": "Related email subject"
    }
  ],
  "deadlines": [
    {
      "deadline": "Exact deadline stated in the email",
      "relatedSubject": "Related email subject"
    }
  ],
  "emails": [
    {
      "subject": "Email subject",
      "sender": "Sender",
      "summary": "One or two sentence summary",
      "priority": "High | Medium | Low",
      "recommendation": "Recommended next step or No action needed"
    }
  ]
}

Rules:
- Do not invent deadlines or facts.
- Ignore obvious advertisements unless they contain a meaningful deadline or account issue.
- Mark security notices, payment issues, deadlines, appointments, and direct requests appropriately.
- Keep the output concise and practical.
          `.trim(),
        },
        {
          role: "user",
          content: emailBatch,
        },
      ],
    });

    const content = completion.choices[0]?.message?.content;

    if (!content) {
      return res.status(500).json({
        error: "No daily summary was generated",
      });
    }

    const cleanedContent = content
      .replace(/^```json\s*/i, "")
      .replace(/```$/i, "")
      .trim();

    const dailySummary = JSON.parse(cleanedContent);

    return res.json(dailySummary);
  } catch (error) {
    console.error("Daily summary failed:", error);

    return res.status(500).json({
      error: "Failed to generate today's Gmail summary",
    });
  }
});

app.listen(port, () => {
  console.log(`Inbox2Done API running on http://localhost:${port}`);
});