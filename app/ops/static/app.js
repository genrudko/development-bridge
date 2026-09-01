(() => {
  let eventSource = null;
  let autoScroll = true;

  const STATUS_LABELS = {
    idle: 'ожидание',
    planning: 'планирование',
    working: 'в работе',
    waiting: 'ожидание',
    blocked: 'заблокировано',
    completed: 'завершено',
    queued: 'в очереди',
    running: 'выполняется',
    succeeded: 'успешно',
    failed: 'ошибка',
    cancelled: 'отменено',
    timed_out: 'тайм-аут',
    interrupted: 'прервано',
    not_found: 'не найдено',
    pending: 'ожидает доставки',
    claimed: 'доставляется',
    owner_input_required: 'нужно действие владельца',
    escalation_due: 'нужна эскалация',
    active: 'активен',
  };

  function getBasePath() {
    if (document.body && document.body.dataset && document.body.dataset.basePath) {
      return document.body.dataset.basePath.replace(/\/$/, '');
    }
    const path = window.location.pathname.replace(/\/$/, '');
    return path || '/ops';
  }

  function getQuery() {
    return (window.location && window.location.search) || '';
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function statusLabel(status) {
    if (!status) return '-';
    return STATUS_LABELS[status] || status;
  }

  function statusClass(status) {
    if (['completed', 'succeeded', 'active'].includes(status)) return 'success';
    if (['working', 'running', 'claimed'].includes(status)) return 'accent';
    if (['failed', 'blocked', 'owner_input_required', 'escalation_due'].includes(status)) return 'danger';
    if (['idle'].includes(status)) return 'secondary';
    return 'warning';
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return `${h} ч ${m} мин ${s} с`;
  }

  function formatDate(value) {
    if (!value) return '-';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('ru-RU');
  }

  function setFocusParam(name, value) {
    const params = new URLSearchParams(getQuery());
    if (value) params.set(name, value);
    else params.delete(name);
    const query = params.toString();
    const target = `${window.location.pathname}${query ? `?${query}` : ''}`;
    window.location.href = target;
  }

  function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        tabButtons.forEach(button => button.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        btn.classList.add('active');
        const activePane = document.getElementById(`tab-${target}`);
        if (activePane) activePane.classList.add('active');
      });
    });
  }

  function initTerminalScroll() {
    const scrollCheckbox = document.getElementById('autoScrollCheckbox');
    const terminalEl = document.getElementById('terminalContent');
    if (scrollCheckbox) {
      scrollCheckbox.addEventListener('change', event => {
        autoScroll = event.target.checked;
      });
    }
    if (terminalEl) {
      terminalEl.addEventListener('scroll', () => {
        const atBottom = terminalEl.scrollHeight - terminalEl.scrollTop <= terminalEl.clientHeight + 40;
        if (scrollCheckbox && autoScroll !== atBottom) {
          autoScroll = atBottom;
          scrollCheckbox.checked = atBottom;
        }
      });
    }
  }

  function initFocusSelectors() {
    const routeSelect = document.getElementById('routeSelect');
    if (routeSelect) {
      routeSelect.addEventListener('change', event => setFocusParam('route_id', event.target.value));
    }
    const terminalJobSelect = document.getElementById('terminalJobSelect');
    if (terminalJobSelect) {
      terminalJobSelect.addEventListener('change', event => setFocusParam('job_id', event.target.value));
    }
  }

  function updateHeader(data) {
    const bridge = data.bridge || {};
    const jobs = data.jobs || {};
    const routes = data.routes || [];
    const activeJobs = jobs.active || [];

    const name = document.getElementById('bridgeName');
    if (name) name.textContent = bridge.name || 'Development Bridge';

    const activeCount = document.getElementById('headerActiveJobs');
    if (activeCount) activeCount.textContent = jobs.active_count !== undefined ? jobs.active_count : activeJobs.length;

    const routeCount = document.getElementById('headerRoutes');
    if (routeCount) routeCount.textContent = routes.length;

    const executors = document.getElementById('headerExecutors');
    if (executors) {
      const counts = new Map();
      activeJobs.forEach(job => {
        const key = job.executor || 'не назначен';
        counts.set(key, (counts.get(key) || 0) + 1);
      });
      executors.textContent = counts.size
        ? Array.from(counts.entries()).map(([nameValue, count]) => `${nameValue}: ${count}`).join(' / ')
        : 'нет';
    }

    const uptime = document.getElementById('headerUptime');
    if (uptime && bridge.uptime_seconds !== undefined) uptime.textContent = formatDuration(bridge.uptime_seconds);
  }

  function updateRouteSelect(data) {
    const select = document.getElementById('routeSelect');
    if (!select) return;
    const routes = data.routes || [];
    const selected = data.route && data.route.route_id;
    if (!routes.length) {
      select.innerHTML = '<option value="">Маршрутов нет</option>';
      return;
    }
    select.innerHTML = routes.map(route => {
      const rid = escapeHtml(route.route_id || '');
      const title = route.title ? ` — ${escapeHtml(route.title)}` : '';
      return `<option value="${rid}"${route.route_id === selected ? ' selected' : ''}>${rid}${title}</option>`;
    }).join('');
  }

  function updateTerminalJobSelect(data) {
    const select = document.getElementById('terminalJobSelect');
    if (!select) return;
    const jobs = (data.jobs && data.jobs.recent) || [];
    const focused = data.jobs && data.jobs.focused ? data.jobs.focused.job_id : null;
    if (!jobs.length) {
      select.innerHTML = '<option value="">Задач нет</option>';
      return;
    }
    select.innerHTML = jobs.map(job => {
      const id = escapeHtml(job.job_id || '');
      const repo = `${escapeHtml(job.project_id || '-')}/${escapeHtml(job.repository_id || '-')}`;
      return `<option value="${id}"${job.job_id === focused ? ' selected' : ''}>${id} — ${repo} — ${escapeHtml(statusLabel(job.status))}</option>`;
    }).join('');
  }

  function updateOverview(data) {
    const progress = data.progress || {};
    const route = data.route || {};
    const jobs = data.jobs || {};
    const activeJobs = jobs.active || [];
    const routes = data.routes || [];

    const activeBadge = document.getElementById('activeJobsBadge');
    if (activeBadge) {
      activeBadge.textContent = jobs.active_count !== undefined ? jobs.active_count : activeJobs.length;
      activeBadge.className = `badge badge-${activeJobs.length ? 'accent' : 'secondary'}`;
    }

    const activeBody = document.getElementById('activeJobsTableBody');
    if (activeBody) {
      if (!activeJobs.length) {
        activeBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Сейчас активных задач нет</td></tr>';
      } else {
        activeBody.innerHTML = activeJobs.map(job => `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 0.8rem;">${escapeHtml(job.job_id)}</td>
            <td>${escapeHtml(job.project_id)}/${escapeHtml(job.repository_id)}</td>
            <td><span class="badge badge-${statusClass(job.status)}">${escapeHtml(statusLabel(job.status))}</span></td>
            <td>${escapeHtml(job.executor || '-')}</td>
            <td>${escapeHtml(job.executor_model || '-')}</td>
            <td>${escapeHtml(formatDate(job.started_at || job.created_at))}</td>
          </tr>
        `).join('');
      }
    }

    const routesBadge = document.getElementById('routesBadge');
    if (routesBadge) routesBadge.textContent = routes.length;

    const routesBody = document.getElementById('routesTableBody');
    if (routesBody) {
      if (!routes.length) {
        routesBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Маршруты не зарегистрированы</td></tr>';
      } else {
        routesBody.innerHTML = routes.map(item => {
          const itemProgress = item.progress || {};
          const hasPercent = itemProgress.percent !== undefined && itemProgress.percent !== null;
          return `
            <tr>
              <td><strong>${escapeHtml(item.route_id || '-')}</strong>${item.default ? ' <span class="badge badge-secondary">по умолчанию</span>' : ''}</td>
              <td>${escapeHtml(item.channel_id || '-')}</td>
              <td><span class="badge badge-${statusClass(item.state)}">${escapeHtml(statusLabel(item.state))}</span></td>
              <td>${escapeHtml(itemProgress.title || 'нет активной работы')}</td>
              <td>${hasPercent ? `${escapeHtml(itemProgress.percent)}%` : '-'}</td>
            </tr>
          `;
        }).join('');
      }
    }

    const title = document.getElementById('progTitle');
    if (title) title.textContent = progress.title || route.title || 'Нет активной работы';

    const status = document.getElementById('progStatus');
    if (status) {
      const value = progress.status || 'idle';
      status.textContent = statusLabel(value);
      status.className = `badge badge-${statusClass(value)}`;
    }

    const hasSemanticPercent = progress.percent !== undefined && progress.percent !== null;
    const percent = hasSemanticPercent ? progress.percent : 0;
    const fill = document.getElementById('progFill');
    if (fill) fill.style.width = `${percent}%`;
    const percentText = document.getElementById('progPercent');
    if (percentText) percentText.textContent = hasSemanticPercent ? `${percent}%` : '0%';

    const phase = document.getElementById('progPhase');
    if (phase) phase.textContent = progress.phase || '-';
    const current = document.getElementById('progCurrent');
    if (current) current.textContent = progress.current || '-';
    const next = document.getElementById('progNext');
    if (next) next.textContent = progress.next || '-';
    const detail = document.getElementById('progDetail');
    if (detail) detail.textContent = progress.detail || '-';
  }

  function updateTerminal(data) {
    const contentEl = document.getElementById('terminalContent');
    const statusEl = document.getElementById('terminalJobStatus');
    const idEl = document.getElementById('terminalJobId');
    const truncEl = document.getElementById('terminalTruncated');

    if (statusEl) {
      statusEl.textContent = statusLabel(data.status || 'idle');
      statusEl.className = `badge badge-${statusClass(data.status || 'idle')}`;
    }
    if (idEl) idEl.textContent = data.job_id || 'нет';
    if (truncEl) truncEl.style.display = (data.stdout_truncated || data.stderr_truncated) ? 'inline-block' : 'none';

    if (contentEl) {
      let content = '';
      if (data.stdout) content += data.stdout;
      if (data.stderr) content += `\n[STDERR]\n${data.stderr}`;
      if (!content) content = '(вывод пока отсутствует)';
      contentEl.textContent = content;
      if (autoScroll) contentEl.scrollTop = contentEl.scrollHeight;
    }
  }

  function updateJobs(data) {
    const jobs = (data.jobs && data.jobs.recent) || [];
    const tbody = document.getElementById('jobsTableBody');
    if (!tbody) return;

    if (!jobs.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Последних задач нет</td></tr>';
      return;
    }

    tbody.innerHTML = jobs.map(job => {
      const executorText = job.executor
        ? `${escapeHtml(job.executor)}${job.executor_model ? ` (${escapeHtml(job.executor_model)})` : ''}`
        : '-';
      const resultText = job.failure_reason
        ? escapeHtml(job.failure_reason)
        : (job.exit_code !== undefined && job.exit_code !== null ? `Код выхода ${escapeHtml(job.exit_code)}` : '-');
      return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 0.8rem;">${escapeHtml(job.job_id)}</td>
          <td>${escapeHtml(job.task_id)}</td>
          <td><span class="badge badge-${statusClass(job.status)}">${escapeHtml(statusLabel(job.status))}</span></td>
          <td>${escapeHtml(job.project_id)}/${escapeHtml(job.repository_id)}</td>
          <td>${executorText}</td>
          <td>${escapeHtml(formatDate(job.created_at))}</td>
          <td>${resultText}</td>
        </tr>
      `;
    }).join('');
  }

  function updateGit(data) {
    const git = data.git;
    const branch = document.getElementById('gitBranch');
    const head = document.getElementById('gitHead');
    const status = document.getElementById('gitCleanStatus');
    const changed = document.getElementById('gitChangedFiles');
    const upstream = document.getElementById('gitUpstream');
    const aheadBehind = document.getElementById('gitAheadBehind');

    if (!git) {
      if (branch) branch.textContent = 'Нет задачи в фокусе';
      if (head) head.textContent = '-';
      if (status) status.textContent = '-';
      if (changed) changed.textContent = '-';
      if (upstream) upstream.textContent = '-';
      if (aheadBehind) aheadBehind.textContent = '-';
      return;
    }

    if (branch) branch.textContent = `${git.branch || 'detached HEAD'} (${git.project_id}/${git.repository_id})`;
    if (head) head.textContent = git.head_short || git.head || '-';
    if (status) {
      status.textContent = git.clean ? 'чистое' : 'есть изменения';
      status.className = `badge badge-${git.clean ? 'success' : 'warning'}`;
    }
    if (changed) changed.textContent = `${git.changed_files_count || 0} файлов`;
    if (upstream) upstream.textContent = git.upstream || 'нет';
    if (aheadBehind) aheadBehind.textContent = `+${git.ahead || 0} / -${git.behind || 0}`;
  }

  function updateWake(data) {
    const wake = data.wake || {};
    const route = data.route || {};
    const channel = document.getElementById('wakeChannel');
    if (channel) channel.textContent = wake.channel_id || route.channel_id || 'coordinator';

    const state = document.getElementById('wakeState');
    if (state) {
      const value = wake.state || 'idle';
      state.textContent = statusLabel(value);
      state.className = `badge badge-${statusClass(value)}`;
    }

    const continuation = document.getElementById('wakeContinuation');
    if (continuation) continuation.textContent = wake.continuation_id || '-';
    const attempts = document.getElementById('wakeAttempts');
    if (attempts) attempts.textContent = `${wake.delivery_attempts || 0} / ${wake.max_delivery_attempts || 1}`;
    const delivered = document.getElementById('wakeDelivered');
    if (delivered) {
      delivered.textContent = wake.transport_delivered
        ? `да${wake.transport_delivered_at ? ` (${new Date(wake.transport_delivered_at * 1000).toLocaleTimeString('ru-RU')})` : ''}`
        : 'нет';
    }
    const transport = document.getElementById('wakeTransport');
    if (transport) transport.textContent = `${wake.last_transport_name || '-'} (${wake.last_transport_disposition || 'нет данных'})`;
    const alert = document.getElementById('wakeOwnerAlert');
    if (alert) alert.style.display = wake.owner_input_required ? 'block' : 'none';
    const cooldown = document.getElementById('wakeCooldown');
    if (cooldown) {
      const seconds = Math.max(wake.retry_after_seconds || 0, wake.web_turn_cooldown_seconds || 0, wake.web_backoff_seconds || 0);
      cooldown.textContent = seconds > 0 ? `${seconds.toFixed(1)} с` : 'нет';
    }
  }

  function updateSystem(data) {
    const sys = data.system || {};
    const mem = sys.memory || {};
    const disk = sys.disk || {};
    const load = sys.load || [];
    const procs = sys.process_counts || {};

    const memEl = document.getElementById('sysMem');
    if (memEl) memEl.textContent = mem.total_gib ? `${mem.available_gib} GiB доступно из ${mem.total_gib} GiB; swap ${mem.swap_used_gib} GiB` : '-';
    const diskEl = document.getElementById('sysDisk');
    if (diskEl) diskEl.textContent = disk.total_gib ? `${disk.free_gib} GiB свободно из ${disk.total_gib} GiB; занято ${disk.used_percent}%` : '-';
    const loadEl = document.getElementById('sysLoad');
    if (loadEl) loadEl.textContent = load.length ? load.join(', ') : '-';
    const procsEl = document.getElementById('sysProcs');
    if (procsEl) procsEl.textContent = `Chromium: ${procs.chromium || 0}, Xvfb: ${procs.xvfb || 0}`;
    const uptime = document.getElementById('sysUptime');
    if (uptime && sys.uptime_seconds !== undefined) uptime.textContent = formatDuration(sys.uptime_seconds);
  }

  function updateAll(data) {
    updateHeader(data);
    updateRouteSelect(data);
    updateTerminalJobSelect(data);
    updateOverview(data);
    updateJobs(data);
    updateGit(data);
    updateWake(data);
    updateSystem(data);
    const updated = document.getElementById('lastUpdated');
    if (updated) updated.textContent = new Date().toLocaleTimeString('ru-RU');
  }

  function connectSSE() {
    const basePath = getBasePath();
    const query = getQuery();
    const connection = document.getElementById('connStatus');
    if (eventSource) eventSource.close();

    if (connection) {
      connection.textContent = 'Подключение...';
      connection.className = 'badge badge-warning';
    }

    eventSource = new EventSource(`${basePath}/api/events${query}`);
    eventSource.onopen = () => {
      if (connection) {
        connection.textContent = 'SSE подключён';
        connection.className = 'badge badge-success';
      }
    };
    eventSource.addEventListener('snapshot', event => {
      try {
        updateAll(JSON.parse(event.data));
      } catch (error) {
        console.error('Не удалось разобрать snapshot SSE:', error);
      }
    });
    eventSource.addEventListener('terminal', event => {
      try {
        updateTerminal(JSON.parse(event.data));
      } catch (error) {
        console.error('Не удалось разобрать terminal SSE:', error);
      }
    });
    eventSource.onerror = () => {
      if (connection) {
        connection.textContent = 'Связь потеряна, переподключение...';
        connection.className = 'badge badge-danger';
      }
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTerminalScroll();
    initFocusSelectors();

    const basePath = getBasePath();
    const query = getQuery();
    fetch(`${basePath}/api/snapshot${query}`)
      .then(response => {
        if (response.status === 401) {
          window.location.href = `${basePath}/login`;
          return null;
        }
        return response.json();
      })
      .then(data => {
        if (data) updateAll(data);
      })
      .catch(console.error);

    connectSSE();
  });
})();
