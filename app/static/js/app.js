const toggleButton = document.querySelector('.menu-toggle');
const menu = document.querySelector('.menu');

if (toggleButton && menu) {
  toggleButton.addEventListener('click', () => {
    const isOpen = menu.classList.toggle('open');
    toggleButton.setAttribute('aria-expanded', String(isOpen));
  });
}

function formatMinutes(minutes) {
  const total = Number(minutes || 0);
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  return `${hours}h ${mins}m`;
}

async function fetchTimeStatus(orderId) {
  const response = await fetch(`/api/orders/${orderId}/time/status`);
  return response.json();
}

async function startTimer(orderId) {
  const response = await fetch(`/api/orders/${orderId}/time/start`, { method: 'POST' });
  return response.json();
}

async function stopTimer(orderId) {
  const response = await fetch(`/api/orders/${orderId}/time/stop`, { method: 'POST' });
  return response.json();
}

function renderTimeStatus(container, payload) {
  const startBtn = container.querySelector('[data-time-start]');
  const stopBtn = container.querySelector('[data-time-stop]');
  const status = container.querySelector('[data-time-running-status]');
  const userTotal = container.querySelector('[data-user-total]');
  const orderTotal = container.querySelector('[data-order-total]');

  const isRunning = Boolean(payload.running);
  startBtn.hidden = isRunning;
  stopBtn.hidden = !isRunning;
  status.textContent = isRunning ? 'W TRAKCIE' : 'ZATRZYMANO';
  userTotal.textContent = formatMinutes(payload.user_total_minutes);
  orderTotal.textContent = formatMinutes(payload.order_total_minutes);
}


function translateTimerError(errorCode) {
  const errorMap = {
    order_status_not_allowed: 'Status zlecenia nie pozwala na uruchomienie timera.',
    active_timer_exists: 'Masz już uruchomiony timer dla innego zlecenia.',
    no_active_timer: 'Brak aktywnego timera do zatrzymania.',
  };
  return errorMap[errorCode] || 'Wystąpił błąd.';
}

async function initOrderTimer() {
  const container = document.querySelector('[data-time-tracker]');
  if (!container) return;

  const orderId = container.dataset.orderId;
  const startBtn = container.querySelector('[data-time-start]');
  const stopBtn = container.querySelector('[data-time-stop]');

  const refresh = async () => {
    try {
      const payload = await fetchTimeStatus(orderId);
      renderTimeStatus(container, payload);
    } catch (error) {
      console.error('Nie udało się pobrać statusu timera', error);
    }
  };

  startBtn.addEventListener('click', async () => {
    const payload = await startTimer(orderId);
    if (!payload.ok) {
      alert(`Nie udało się uruchomić timera: ${translateTimerError(payload.error)}`);
      return;
    }
    await refresh();
  });

  stopBtn.addEventListener('click', async () => {
    const payload = await stopTimer(orderId);
    if (!payload.ok) {
      alert(`Nie udało się zatrzymać timera: ${translateTimerError(payload.error)}`);
      return;
    }
    await refresh();
    window.location.reload();
  });

  await refresh();
  setInterval(refresh, 15000);
}

initOrderTimer();
