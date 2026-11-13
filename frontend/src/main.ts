import { fetchHealth, getApiBaseUrl } from './health.ts';

const serviceBadge = document.getElementById('service-badge') as HTMLSpanElement;
const backendEndpoint = document.getElementById('backend-endpoint') as HTMLElement;
const serviceVersion = document.getElementById('service-version') as HTMLSpanElement;
const dbStatusBadge = document.getElementById('db-status-badge') as HTMLSpanElement;
const dbValueDisplay = document.getElementById('db-value-display') as HTMLDivElement;
const dbMessageDisplay = document.getElementById('db-message-display') as HTMLDivElement;
const refreshBtn = document.getElementById('refresh-btn') as HTMLButtonElement;
const lastChecked = document.getElementById('last-checked') as HTMLSpanElement;

export async function checkSystemHealth(): Promise<void> {
  const currentBaseUrl = getApiBaseUrl();
  backendEndpoint.textContent = `${currentBaseUrl}/api/health`;

  refreshBtn.disabled = true;
  serviceBadge.className = 'badge badge-neutral';
  serviceBadge.textContent = 'Checking...';

  dbStatusBadge.className = 'badge badge-neutral';
  dbStatusBadge.textContent = 'Checking...';

  dbValueDisplay.textContent = 'Querying backend & database...';
  dbMessageDisplay.textContent = '';

  try {
    const { data } = await fetchHealth();

    // 1. Service Status
    if (data.status === 'healthy') {
      serviceBadge.className = 'badge badge-success';
      serviceBadge.textContent = 'Online (200 OK)';
    } else {
      serviceBadge.className = 'badge badge-warning';
      serviceBadge.textContent = data.status.toUpperCase();
    }

    serviceVersion.textContent = `${data.service} v${data.version}`;

    // 2. Database Status & Value
    const db = data.database;
    if (db) {
      if (db.status === 'connected') {
        dbStatusBadge.className = 'badge badge-success';
        dbStatusBadge.textContent = 'Connected';
        dbValueDisplay.textContent = db.value || 'Connected (no value returned)';
        dbMessageDisplay.textContent = db.message || 'Database connection verified.';
      } else if (db.status === 'disconnected') {
        dbStatusBadge.className = 'badge badge-warning';
        dbStatusBadge.textContent = 'Disconnected';
        dbValueDisplay.textContent = 'No database configured yet';
        dbMessageDisplay.textContent = db.message || 'Set SUPABASE_URL and SUPABASE_SERVICE_KEY in backend .env';
      } else {
        dbStatusBadge.className = 'badge badge-error';
        dbStatusBadge.textContent = 'Error';
        dbValueDisplay.textContent = 'Failed to read from database';
        dbMessageDisplay.textContent = db.message || 'Check database connectivity and credentials.';
      }
    } else {
      dbStatusBadge.className = 'badge badge-neutral';
      dbStatusBadge.textContent = 'N/A';
      dbValueDisplay.textContent = 'No database metadata returned';
    }

    lastChecked.textContent = `Last check: ${new Date().toLocaleTimeString()}`;
  } catch (error: unknown) {
    serviceBadge.className = 'badge badge-error';
    serviceBadge.textContent = 'Offline';

    dbStatusBadge.className = 'badge badge-error';
    dbStatusBadge.textContent = 'Unreachable';

    dbValueDisplay.textContent = 'Could not reach backend service';
    const errorMessage = error instanceof Error ? error.message : 'Check if the backend server is running.';
    dbMessageDisplay.textContent = errorMessage;

    lastChecked.textContent = `Failed: ${new Date().toLocaleTimeString()}`;
  } finally {
    refreshBtn.disabled = false;
  }
}

refreshBtn.addEventListener('click', () => {
  void checkSystemHealth();
});

// Initial health check on page load
void checkSystemHealth();
