import { useEffect, useState } from "react";
import {
  Alert,
  AppShell,
  Badge,
  Button,
  Container,
  Divider,
  Drawer,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconBrandGoogle,
  IconChevronRight,
  IconMail,
  IconRefresh,
  IconSparkles,
} from "@tabler/icons-react";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type GoogleStatus = {
  connected: boolean;
  user_id?: number;
  email?: string;
  display_name?: string;
};

type BillingStatus = {
  plan: string;
  daily_limit: number;
  used_today: number;
  remaining_today: number;
};

type CheckoutSession = {
  checkout_url: string;
};

type EmailThread = {
  id: number;
  user_id: number;
  gmail_thread_id: string;
  subject: string;
  snippet: string;
  participants: string;
  message_count: number;
  latest_message_at: string | null;
  created_at: string;
  updated_at: string;
};

type EmailMessage = {
  id: number;
  thread_id: number;
  gmail_message_id: string;
  sender: string;
  recipients: string;
  cc: string;
  subject: string;
  snippet: string;
  body_text: string;
  body_html: string;
  attachment_metadata: unknown[];
  sent_at: string | null;
  created_at: string;
  updated_at: string;
};

type ThreadDetail = EmailThread & {
  messages: EmailMessage[];
};

type ThreadPage = {
  items: EmailThread[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
};

type ThreadAnalysis = {
  id: number;
  thread_id: number;
  model_name: string;
  source_fingerprint: string;
  summary: string;
  category: string;
  priority: string;
  sentiment: string;
  created_at: string;
  updated_at: string;
  action_items: unknown[];
  suggested_replies: unknown[];
};

type QueuedJob = {
  job_id: number;
  task_id: string;
  status: string;
};

function App() {
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [threads, setThreads] = useState<EmailThread[]>([]);

  const [selectedThread, setSelectedThread] =
    useState<ThreadDetail | null>(null);

  const [analysis, setAnalysis] =
    useState<ThreadAnalysis | null>(null);

  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [upgrading, setUpgrading] = useState(false);

  const [error, setError] = useState("");

  async function apiFetch(
    path: string,
    options: RequestInit = {},
  ) {
    return fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: "include",
    });
  }

  async function loadStatus() {
    const response = await apiFetch("/api/auth/google/status");

    if (!response.ok) {
      throw new Error(
        "Could not load Google connection status.",
      );
    }

    const data: GoogleStatus = await response.json();
    setGoogle(data);

    return data;
  }

  async function loadBillingStatus() {
    const response = await apiFetch("/api/billing/status");

    if (!response.ok) {
      throw new Error("Could not load billing status.");
    }

    const data: BillingStatus = await response.json();
    setBilling(data);

    return data;
  }

  async function loadThreads() {
    const response = await apiFetch(
      "/api/threads?page=1&page_size=10",
    );

    if (!response.ok) {
      throw new Error("Could not load email threads.");
    }

    const data: ThreadPage = await response.json();
    setThreads(data.items);
  }

  async function upgradeToPro() {
  setUpgrading(true);
  setError("");

  try {
    const response = await apiFetch("/api/billing/checkout", {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error("Could not start Stripe Checkout.");
    }

    const data: CheckoutSession = await response.json();

    window.location.assign(data.checkout_url);
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Could not start Stripe Checkout.",
    );
    setUpgrading(false);
  }
}

  async function loadDashboard() {
    setLoading(true);
    setError("");

    try {
      const status = await loadStatus();

      if (status.connected) {
        await Promise.all([
          loadThreads(),
          loadBillingStatus(),
        ]);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openThread(threadId: number) {
    setThreadLoading(true);
    setError("");
    setAnalysis(null);

    try {
      const response = await apiFetch(
        `/api/threads/${threadId}`,
      );

      if (!response.ok) {
        throw new Error("Could not load thread.");
      }

      const detail: ThreadDetail = await response.json();
      setSelectedThread(detail);

      const analysisResponse = await apiFetch(
        `/api/threads/${threadId}/analysis`,
      );

      if (analysisResponse.ok) {
        const savedAnalysis: ThreadAnalysis =
          await analysisResponse.json();

        setAnalysis(savedAnalysis);
      } else if (analysisResponse.status !== 404) {
        throw new Error(
          "Could not load thread analysis.",
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not open thread.",
      );
    } finally {
      setThreadLoading(false);
    }
  }

  async function syncGmail() {
    setSyncing(true);
    setError("");

    try {
      const response = await apiFetch(
        "/api/gmail/sync?max_threads=10",
        {
          method: "POST",
        },
      );

      if (!response.ok) {
        const body = await response.json();

        throw new Error(
          body.message ?? "Gmail sync failed.",
        );
      }

      const job: QueuedJob = await response.json();

      await pollJob(job.job_id);
      await loadThreads();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Gmail sync failed.",
      );
    } finally {
      setSyncing(false);
    }
  }

  async function analyzeThread() {
    if (!selectedThread) {
      return;
    }

    setAnalyzing(true);
    setError("");

    try {
      const response = await apiFetch(
        `/api/threads/${selectedThread.id}/analyze?force=true`,
        {
          method: "POST",
        },
      );

      if (!response.ok) {
        const body = await response.json();

        if (response.status === 429) {
          await loadBillingStatus().catch(() => undefined);
        }

        throw new Error(
          body.message ?? "Could not start analysis.",
        );
      }

      const queued: QueuedJob = await response.json();

      await loadBillingStatus().catch(() => undefined);

      await pollJob(queued.job_id);

      const analysisResponse = await apiFetch(
        `/api/threads/${selectedThread.id}/analysis`,
      );

      if (!analysisResponse.ok) {
        throw new Error(
          "Analysis finished but could not be loaded.",
        );
      }

      const result: ThreadAnalysis =
        await analysisResponse.json();

      setAnalysis(result);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Thread analysis failed.",
      );
    } finally {
      setAnalyzing(false);
    }
  }

  async function pollJob(jobId: number) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const response = await apiFetch(
        `/api/jobs/${jobId}`,
      );

      if (!response.ok) {
        throw new Error(
          "Could not check background job.",
        );
      }

      const job = await response.json();

      if (job.status === "succeeded") {
        return;
      }

      if (job.status === "failed") {
        throw new Error(
          job.error_message ??
            "Background job failed.",
        );
      }

      await new Promise((resolve) =>
        setTimeout(resolve, 1000),
      );
    }

    throw new Error("Background job timed out.");
  }

  function connectGoogle() {
    window.open(
      `${API_BASE}/api/auth/google/login`,
      "_blank",
      "noopener,noreferrer",
    );
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  const dailyLimitReached =
    billing !== null &&
    billing.remaining_today === 0;

  return (
    <AppShell header={{ height: 64 }}>
      <AppShell.Header>
        <Container size="lg" h="100%">
          <Group
            h="100%"
            justify="space-between"
          >
            <Group>
              <IconMail size={26} />
              <Title order={3}>Inbox2Done</Title>
            </Group>

            <Group>
              {billing && (
                <Badge
                  color={
                    billing.plan === "pro"
                      ? "violet"
                      : "gray"
                  }
                  variant="light"
                >
                  {billing.plan.toUpperCase()}
                </Badge>
              )}

              <Badge
                color={
                  google?.connected
                    ? "green"
                    : "gray"
                }
                variant="light"
              >
                {google?.connected
                  ? "Gmail Connected"
                  : "Gmail Not Connected"}
              </Badge>
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="lg" py="xl">
          <Stack gap="lg">
            <div>
              <Title order={1}>Inbox</Title>

              <Text c="dimmed">
                Turn Gmail threads into actionable work.
              </Text>
            </div>

            {error && (
              <Alert
                color="red"
                icon={
                  <IconAlertCircle size={18} />
                }
              >
                {error}
              </Alert>
            )}

            {loading ? (
              <Group>
                <Loader size="sm" />
                <Text>
                  Loading Inbox2Done...
                </Text>
              </Group>
            ) : !google?.connected ? (
              <Paper
                withBorder
                radius="lg"
                p="xl"
              >
                <Stack align="flex-start">
                  <Title order={3}>
                    Connect Gmail
                  </Title>

                  <Text c="dimmed">
                    Connect Google to synchronize
                    your inbox.
                  </Text>
                  <Button
                    leftSection={
                      <IconBrandGoogle
                        size={18}
                      />
                    }
                    onClick={connectGoogle}
                  >
                    Connect Google
                  </Button>

                  <Button
                    variant="subtle"
                    onClick={() =>
                      void loadDashboard()
                    }
                  >
                    I finished connecting
                  </Button>
                </Stack>
              </Paper>
            ) : (
              <>
                <Group justify="space-between">
                  <div>
                    <Text fw={600}>
                      {google.display_name ??
                        google.email}
                    </Text>

                    <Text
                      size="sm"
                      c="dimmed"
                    >
                      {google.email}
                    </Text>
                  </div>

                  <Button
                    leftSection={
                      syncing ? (
                        <Loader size={16} />
                      ) : (
                        <IconRefresh
                          size={18}
                        />
                      )
                    }
                    onClick={() =>
                      void syncGmail()
                    }
                    disabled={syncing}
                  >
                    {syncing
                      ? "Syncing..."
                      : "Sync Gmail"}
                  </Button>
                </Group>

                <Paper
                  withBorder
                  radius="lg"
                  p="md"
                >
                  <Group justify="space-between">
                    <div>
                      <Group gap="xs">
                        <Text fw={600}>
                          AI Usage
                        </Text>

                        <Badge
                          color={
                            billing?.plan === "pro"
                              ? "violet"
                              : "gray"
                          }
                          variant="light"
                        >
                          {billing
                            ? `${billing.plan.toUpperCase()} PLAN`
                            : "Loading plan..."}
                        </Badge>
                      </Group>

                      <Text
                        size="sm"
                        c="dimmed"
                        mt="xs"
                      >
                        {billing
                          ? `${billing.remaining_today} of ${billing.daily_limit} AI analyses remaining today`
                          : "Loading usage..."}
                      </Text>
                    </div>

                    {billing?.plan !== "pro" && (
                      <Button
                        onClick={upgradeToPro}
                        loading={upgrading}
                      >
                        Upgrade to Pro
                      </Button>
                    )}
                  </Group>
                </Paper>

                <Paper
                  withBorder
                  radius="lg"
                >
                  <Group
                    justify="space-between"
                    p="md"
                  >
                    <Title order={3}>
                      Recent Threads
                    </Title>

                    <Badge variant="light">
                      {threads.length}
                    </Badge>
                  </Group>

                  <Stack gap={0}>
                    {threads.map(
                      (thread) => (
                        <Paper
                          key={thread.id}
                          p="md"
                          radius={0}
                          onClick={() =>
                            void openThread(
                              thread.id,
                            )
                          }
                          style={{
                            cursor: "pointer",
                            borderTop:
                              "1px solid var(--mantine-color-gray-2)",
                          }}
                        >
                          <Group
                            justify="space-between"
                            wrap="nowrap"
                          >
                            <div
                              style={{
                                minWidth: 0,
                              }}
                            >
                              <Text fw={600}>
                                {thread.subject ||
                                  "(No subject)"}
                              </Text>

                              <Text
                                size="sm"
                                c="dimmed"
                                lineClamp={1}
                              >
                                {
                                  thread.participants
                                }
                              </Text>
                            </div>

                            <IconChevronRight
                              size={18}
                            />
                          </Group>
                        </Paper>
                      ),
                    )}
                  </Stack>
                </Paper>
              </>
            )}
          </Stack>
        </Container>
      </AppShell.Main>

      <Drawer
        opened={selectedThread !== null}
        onClose={() => {
          setSelectedThread(null);
          setAnalysis(null);
        }}
        position="right"
        size="xl"
        title="Thread"
      >
        {threadLoading ||
        !selectedThread ? (
          <Group>
            <Loader size="sm" />
            <Text>
              Loading thread...
            </Text>
          </Group>
        ) : (
          <Stack>
            <div>
              <Title order={2}>
                {selectedThread.subject}
              </Title>

              <Text
                size="sm"
                c="dimmed"
                mt="xs"
              >
                {selectedThread.participants}
              </Text>
            </div>

            <Group>
              <Button
                leftSection={
                  analyzing ? (
                    <Loader size={16} />
                  ) : (
                    <IconSparkles
                      size={18}
                    />
                  )
                }
                onClick={() =>
                  void analyzeThread()
                }
                disabled={
                  analyzing ||
                  dailyLimitReached
                }
              >
                {analyzing
                  ? "Analyzing..."
                  : dailyLimitReached
                    ? "Daily Limit Reached"
                    : analysis
                      ? "Analyze Again"
                      : "Analyze Thread"}
              </Button>

              {analysis && (
                <Badge
                  color="green"
                  variant="light"
                >
                  AI Analysis Ready
                </Badge>
              )}

              {billing && (
                <Badge variant="outline">
                  {billing.remaining_today}{" "}
                  remaining today
                </Badge>
              )}
            </Group>

            {dailyLimitReached &&
              billing?.plan !== "pro" && (
                <Alert
                  color="yellow"
                  icon={
                    <IconSparkles
                      size={18}
                    />
                  }
                >
                  You have used your free AI
                  analysis for today. Upgrade
                  to Pro for higher usage
                  limits.
                </Alert>
              )}

            {analysis && (
              <Paper
                withBorder
                radius="lg"
                p="md"
              >
                <Stack>
                  <Group justify="space-between">
                    <Title order={3}>
                      AI Analysis
                    </Title>

                    <Group gap="xs">
                      <Badge>
                        {analysis.priority}
                      </Badge>

                      <Badge variant="light">
                        {analysis.category}
                      </Badge>
                    </Group>
                  </Group>

                  <Divider />

                  <div>
                    <Text fw={600}>
                      Summary
                    </Text>

                    <Text mt="xs">
                      {analysis.summary}
                    </Text>
                  </div>

                  <Group gap="xs">
                    <Text
                      size="sm"
                      c="dimmed"
                    >
                      Sentiment:
                    </Text>

                    <Badge
                      size="sm"
                      variant="outline"
                    >
                      {analysis.sentiment}
                    </Badge>
                  </Group>

                  <Text
                    size="xs"
                    c="dimmed"
                  >
                    Model:{" "}
                    {analysis.model_name}
                  </Text>
                </Stack>
              </Paper>
            )}

            <Divider label="Messages" />

            {selectedThread.messages.map(
              (message) => (
                <Paper
                  key={message.id}
                  withBorder
                  radius="lg"
                  p="md"
                >
                  <Stack>
                    <div>
                      <Text fw={600}>
                        {message.sender}
                      </Text>

                      <Text
                        size="xs"
                        c="dimmed"
                      >
                        To:{" "}
                        {message.recipients}
                      </Text>

                      {message.sent_at && (
                        <Text
                          size="xs"
                          c="dimmed"
                        >
                          {new Date(
                            message.sent_at,
                          ).toLocaleString()}
                        </Text>
                      )}
                    </div>

                    <Divider />

                    <ScrollArea.Autosize
                      mah={500}
                    >
                      <Text
                        size="sm"
                        style={{
                          whiteSpace:
                            "pre-wrap",
                        }}
                      >
                        {message.body_text ||
                          message.snippet ||
                          "No readable message body."}
                      </Text>
                    </ScrollArea.Autosize>
                  </Stack>
                </Paper>
              ),
            )}
          </Stack>
        )}
      </Drawer>
    </AppShell>
  );
}

export default App;