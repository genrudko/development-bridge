(() => {
  let eventSource = null;
  let autoScroll = true;
  let currentSnapshot = null;

  function getBasePath() {
    if (document.body && document.body.dataset && document.body.dataset.basePath) {
      return document.body.dataset.basePath.replace(/\/$/, '');
    }
    const path = window.location.pathname.replace(/\/$/, '');
    return path || '/ops';
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

  function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        tabButtons.forEach(b => b.classList.remove('active'));
        tabPanes.forEach(p => p.classList.remove('active'));
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
      scrollCheckbox.addEventListener('change', (e) => {
        autoScroll = e.target.checked;
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

  function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  }

  function updateHeader(data) {
    const bridge = data.bridge || {};
    const route = data.route || {};
    const executor = data.executor || {};
    const jobs = data.jobs || {};

    const elName = document.getElementById('bridgeName');
    if (elName) elName.textContent = bridge.name || 'Development Bridge';

    const elRoute = document.getElementById('headerRoute');
    if (elRoute) elRoute.textContent = route.route_id ? `${route.route_id} (${route.channel_id || 'default'})` : 'No route';

    const elExec = document.getElementById('headerExecutor');
    if (elExec) {
      if (executor.executor) {
        elExec.textContent = `${executor.executor}${executor.model ? ` (${executor.model})` : ''}`;
      } else {
        elExec.textContent = 'None';
      }
    }

    const elUptime = document.getElementById('headerUptime');
    if (elUptime && bridge.uptime_seconds !== undefined) {
      const u = bridge.uptime_seconds;
      const h = Math.floor(u / 3600);
      const m = Math.floor((u % 3600) / 60);
      const s = u % 60;
      elUptime.textContent = `${h}h ${m}m ${s}s`;
    }
  }

  function updateOverview(data) {
    const progress = data.progress || {};
    const route = data.route || {};
    const jobs = data.jobs || {};

    const elProgTitle = document.getElementById('progTitle');
    if (elProgTitle) elProgTitle.textContent = progress.title || (route.title || 'No active progress');

    const elProgStatus = document.getElementById('progStatus');
    if (elProgStatus) {
      const st = progress.status || (jobs.current ? jobs.current.status : 'idle');
      elProgStatus.textContent = st;
      elProgStatus.className = `badge badge-${st === 'completed' || st === 'succeeded' ? 'success' : st === 'working' || st === 'running' ? 'accent' : 'warning'}`;
    }

    const hasSemanticPercent = progress.percent !== undefined && progress.percent !== null;
    const percent = hasSemanticPercent ? progress.percent : 0;
    const elProgFill = document.getElementById('progFill');
    if (elProgFill) elProgFill.style.width = `${percent}%`;

    const elProgPercent = document.getElementById('progPercent');
    if (elProgPercent) elProgPercent.textContent = hasSemanticPercent ? `${percent}%` : '0%';

    const elProgPhase = document.getElementById('progPhase');
    if (elProgPhase) elProgPhase.textContent = progress.phase || '-';

    const elProgCurrent = document.getElementById('progCurrent');
    if (elProgCurrent) elProgCurrent.textContent = progress.current || '-';

    const elProgNext = document.getElementById('progNext');
    if (elProgNext) elProgNext.textContent = progress.next || '-';

    const elProgDetail = document.getElementById('progDetail');
    if (elProgDetail) elProgDetail.textContent = progress.detail || '-';

    // Active / Last job card
    const active = jobs.current || jobs.last;
    const elActiveId = document.getElementById('overviewJobId');
    if (elActiveId) elActiveId.textContent = active ? active.job_id : 'None';

    const elActiveStatus = document.getElementById('overviewJobStatus');
    if (elActiveStatus) elActiveStatus.textContent = active ? active.status : '-';
  }

  function updateTerminal(data) {
    const el = document.getElementById('terminalContent');
    const elStatus = document.getElementById('terminalJobStatus');
    const elId = document.getElementById('terminalJobId');
    const elTrunc = document.getElementById('terminalTruncated');

    if (elStatus) elStatus.textContent = data.status || 'idle';
    if (elId) elId.textContent = data.job_id || 'None';
    if (elTrunc) elTrunc.style.display = (data.stdout_truncated || data.stderr_truncated) ? 'inline-block' : 'none';

    if (el) {
      let content = '';
      if (data.stdout) content += data.stdout;
      if (data.stderr) content += `\n[STDERR]\n${data.stderr}`;
      if (!content) content = '(no output recorded)';
      el.textContent = content;

      if (autoScroll) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }

  function updateJobs(data) {
    const jobs = (data.jobs && data.jobs.recent) || [];
    const tbody = document.getElementById('jobsTableBody');
    if (!tbody) return;

    if (jobs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No recent jobs</td></tr>';
      return;
    }

    tbody.innerHTML = jobs.map(j => {
      const statusClass = j.status === 'succeeded' ? 'success' : j.status === 'failed' ? 'danger' : j.status === 'running' ? 'accent' : 'warning';
      const execModel = j.executor_model ? ` (${escapeHtml(j.executor_model)})` : '';
      const executorText = j.executor ? `${escapeHtml(j.executor)}${execModel}` : '-';
      const resultText = j.failure_reason
        ? escapeHtml(j.failure_reason)
        : (j.exit_code !== undefined && j.exit_code !== null ? `Exit ${escapeHtml(j.exit_code)}` : '-');

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 0.8rem;">${escapeHtml(j.job_id)}</td>
          <td>${escapeHtml(j.task_id)}</td>
          <td><span class="badge badge-${escapeHtml(statusClass)}">${escapeHtml(j.status)}</span></td>
          <td>${escapeHtml(j.project_id)}/${escapeHtml(j.repository_id)}</td>
          <td>${executorText}</td>
          <td>${escapeHtml(j.created_at || '-')}</td>
          <td>${resultText}</td>
        </tr>
      `;
    }).join('');
  }

  function updateGit(data) {
    const git = data.git;
    const pane = document.getElementById('tab-git');
    if (!pane) return;

    const elBranch = document.getElementById('gitBranch');
    const elHead = document.getElementById('gitHead');
    const elStatus = document.getElementById('gitCleanStatus');
    const elChanged = document.getElementById('gitChangedFiles');
    const elUpstream = document.getElementById('gitUpstream');
    const elAheadBehind = document.getElementById('gitAheadBehind');

    if (!git) {
      if (elBranch) elBranch.textContent = 'No active repository';
      if (elHead) elHead.textContent = '-';
      if (elStatus) elStatus.textContent = '-';
      if (elChanged) elChanged.textContent = '-';
      if (elUpstream) elUpstream.textContent = '-';
      if (elAheadBehind) elAheadBehind.textContent = '-';
      return;
    }

    if (elBranch) elBranch.textContent = `${git.branch || 'Detached HEAD'} (${git.project_id}/${git.repository_id})`;
    if (elHead) elHead.textContent = git.head_short || git.head || '-';
    if (elStatus) {
      elStatus.textContent = git.clean ? 'Clean' : 'Dirty';
      elStatus.className = `badge badge-${git.clean ? 'success' : 'warning'}`;
    }
    if (elChanged) elChanged.textContent = `${git.changed_files_count || 0} files`;
    if (elUpstream) elUpstream.textContent = git.upstream || 'None';
    if (elAheadBehind) elAheadBehind.textContent = `+${git.ahead || 0} / -${git.behind || 0}`;
  }

  function updateWake(data) {
    const wake = data.wake || {};
    const route = data.route || {};

    const elChan = document.getElementById('wakeChannel');
    if (elChan) elChan.textContent = wake.channel_id || route.channel_id || 'coordinator';

    const elState = document.getElementById('wakeState');
    if (elState) {
      const st = wake.state || 'idle';
      elState.textContent = st;
      elState.className = `badge badge-${st === 'idle' ? 'secondary' : st === 'pending' || st === 'claimed' ? 'accent' : st === 'owner_input_required' || st === 'escalation_due' ? 'danger' : 'warning'}`;
    }

    const elCont = document.getElementById('wakeContinuation');
    if (elCont) elCont.textContent = wake.continuation_id || '-';

    const elAttempts = document.getElementById('wakeAttempts');
    if (elAttempts) elAttempts.textContent = `${wake.delivery_attempts || 0} / ${wake.max_delivery_attempts || 1}`;

    const elDelivered = document.getElementById('wakeDelivered');
    if (elDelivered) elDelivered.textContent = wake.transport_delivered ? `Yes (${wake.transport_delivered_at ? new Date(wake.transport_delivered_at * 1000).toLocaleTimeString() : 'delivered'})` : 'No';

    const elTransport = document.getElementById('wakeTransport');
    if (elTransport) elTransport.textContent = `${wake.last_transport_name || '-'} (${wake.last_transport_disposition || 'none'})`;

    const elOwnerAlert = document.getElementById('wakeOwnerAlert');
    if (elOwnerAlert) elOwnerAlert.style.display = wake.owner_input_required ? 'block' : 'none';

    const elCooldown = document.getElementById('wakeCooldown');
    if (elCooldown) {
      const cd = Math.max(wake.retry_after_seconds || 0, wake.web_turn_cooldown_seconds || 0, wake.web_backoff_seconds || 0);
      elCooldown.textContent = cd > 0 ? `${cd.toFixed(1)}s` : 'None';
    }
  }

  function updateSystem(data) {
    const sys = data.system || {};
    const mem = sys.memory || {};
    const disk = sys.disk || {};
    const load = sys.load || [];
    const procs = sys.process_counts || {};

    const elMem = document.getElementById('sysMem');
    if (elMem) elMem.textContent = mem.total_gib ? `${mem.available_gib} GiB avail / ${mem.total_gib} GiB (Swap: ${mem.swap_used_gib} GiB)` : '-';

    const elDisk = document.getElementById('sysDisk');
    if (elDisk) elDisk.textContent = disk.total_gib ? `${disk.free_gib} GiB free / ${disk.total_gib} GiB (${disk.used_percent}% used)` : '-';

    const elLoad = document.getElementById('sysLoad');
    if (elLoad) elLoad.textContent = load.length ? load.join(', ') : '-';

    const elProcs = document.getElementById('sysProcs');
    if (elProcs) elProcs.textContent = `Chromium: ${procs.chromium || 0}, Xvfb: ${procs.xvfb || 0}`;

    const elUptime = document.getElementById('sysUptime');
    if (elUptime && sys.uptime_seconds !== undefined) {
      const u = sys.uptime_seconds;
      const h = Math.floor(u / 3600);
      const m = Math.floor((u % 3600) / 60);
      const s = u % 60;
      elUptime.textContent = `${h}h ${m}m ${s}s`;
    }
  }

  function updateAll(data) {
    currentSnapshot = data;
    updateHeader(data);
    updateOverview(data);
    updateJobs(data);
    updateGit(data);
    updateWake(data);
    updateSystem(data);

    const elLastUpdated = document.getElementById('lastUpdated');
    if (elLastUpdated) elLastUpdated.textContent = new Date().toLocaleTimeString();
  }

  function connectSSE() {
    const basePath = getBasePath();
    const query = window.location.search || '';
    const elConn = document.getElementById('connStatus');
    if (eventSource) {
      eventSource.close();
    }

    if (elConn) {
      elConn.textContent = 'Connecting...';
      elConn.className = 'badge badge-warning';
    }

    eventSource = new EventSource(`${basePath}/api/events${query}`);

    eventSource.onopen = () => {
      if (elConn) {
        elConn.textContent = 'Live SSE Connected';
        elConn.className = 'badge badge-success';
      }
    };

    eventSource.addEventListener('snapshot', (e) => {
      try {
        const data = JSON.parse(e.data);
        updateAll(data);
      } catch (err) {
        console.error('Failed to parse snapshot SSE:', err);
      }
    });

    eventSource.addEventListener('terminal', (e) => {
      try {
        const data = JSON.parse(e.data);
        updateTerminal(data);
      } catch (err) {
        console.error('Failed to parse terminal SSE:', err);
      }
    });

    eventSource.onerror = () => {
      if (elConn) {
        elConn.textContent = 'Disconnected (Reconnecting...)';
        elConn.className = 'badge badge-danger';
      }
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTerminalScroll();

    const basePath = getBasePath();
    const query = window.location.search || '';

    // Initial fetch
    fetch(`${basePath}/api/snapshot${query}`)
      .then(res => {
        if (res.status === 401) {
          window.location.href = `${basePath}/login`;
          return;
        }
        return res.json();
      })
      .then(data => {
        if (data) {
          updateAll(data);
        }
      })
      .catch(console.error);

    connectSSE();
  });
})();
