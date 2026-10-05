<script>
  let session = null;
  let logs = [];
  let limits = [];
  let history = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  // 新单点选档位：value 与入库 grade 同口径（soft / hard），漏选不允许提交
  let grade = "";
  let error = "";
  let okMsg = "";
  let loading = false;
  let timer;
  let view = "logs"; // logs（台账） | zoning（围岩分带专页）

  $: isWriter = session?.role === "writer";

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
    if (view === "zoning") await refreshZoning();
  }

  async function refreshZoning() {
    const [lr, hr] = await Promise.all([
      fetch("/api/limits", { headers: headers() }),
      fetch("/api/limits/history", { headers: headers() }),
    ]);
    if (lr.ok) limits = await lr.json();
    if (hr.ok) history = await hr.json();
  }

  async function switchView(v) {
    view = v;
    error = "";
    okMsg = "";
    if (v === "zoning") await refreshZoning();
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    limits = [];
    history = [];
    view = "logs";
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    okMsg = "";
    if (!grade) {
      // 漏选等级整份退回，前后端同口径拦一道
      error = "必须点选围岩等级（软岩/硬岩），漏选整份退回";
      return;
    }
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, delta_mm: Number(deltaMm), grade }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      grade = "";
      okMsg = "已提交，等待后台认领，认领时将抄录该档当前闭区间作为快照";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  // 上块填档位：每档一份本地草稿，默认取当前档位值
  let drafts = {};
  $: if (limits.length) {
    for (const l of limits) {
      if (!(l.grade in drafts)) drafts[l.grade] = { lower_mm: String(l.lower_mm), upper_mm: String(l.upper_mm) };
    }
  }

  async function saveLimit(g) {
    error = "";
    okMsg = "";
    const d = drafts[g];
    const res = await fetch("/api/limits", {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...headers() },
      body: JSON.stringify({ grade: g, lower_mm: Number(d.lower_mm), upper_mm: Number(d.upper_mm) }),
    });
    const data = await res.json();
    if (!res.ok) {
      error = data.detail || "改档失败";
      return;
    }
    okMsg = `${data.grade_label}闭区间已改为 [${data.lower_mm}, ${data.upper_mm}] mm，履历已追加；新认领单据按新区间判定`;
    await refreshZoning();
  }

  function fmt(v) {
    return v === null || v === undefined ? "—" : Number(v).toString();
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 1020px; margin: 0 auto; padding: 1.5rem; }
  header.top {
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 2px solid #d97706; padding-bottom: 0.75rem; margin-bottom: 1.25rem;
  }
  h1 { color: #fbbf24; margin: 0; font-size: 1.35rem; }
  nav { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
  nav button { background: #44403c; }
  nav button.active { background: #d97706; }
  .who { color: #a8a29e; font-size: 0.85rem; text-align: right; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  h2 { font-size: 1.05rem; margin: 0 0 0.25rem; color: #fcd34d; }
  h3 { font-size: 0.95rem; margin: 0 0 0.5rem; color: #d6d3d1; }
  .block-hint { color: #a8a29e; font-size: 0.82rem; margin: 0 0 0.75rem; }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.secondary { background: #57534e; }
  button:disabled { cursor: not-allowed; opacity: 0.6; }
  .err { color: #fb7185; }
  .ok-msg { color: #86efac; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .grade-soft { background: #1e3a5f; color: #93c5fd; }
  .grade-hard { background: #4a1d3f; color: #f0abfc; }
  .empty { color: #78716c; font-size: 0.85rem; padding: 0.5rem 0; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  .card { background: #1f1c1a; border: 1px solid #44403c; border-radius: 6px; padding: 0.75rem; }
  .card .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .mono { font-family: ui-monospace, monospace; }
</style>

<main>
  {#if !session}
    <h1>隧道收敛测缝台</h1>
    <p class="sub">测量员提交桩号、围岩等级与收敛毫米值，接口进程内线程认领后按该档闭区间出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <header class="top">
      <div>
        <h1>隧道收敛测缝台</h1>
        <nav>
          <button class={view === "logs" ? "active" : ""} on:click={() => switchView("logs")}>收敛台账</button>
          <button class={view === "zoning" ? "active" : ""} on:click={() => switchView("zoning")}>围岩分带</button>
        </nav>
      </div>
      <div class="who">
        <div>{session.username}（{isWriter ? "测量员·可报数改档" : "巡检员·只读"}）</div>
        <button class="secondary" on:click={logout}>退出</button>
      </div>
    </header>

    {#if error}<p class="err">{error}</p>{/if}
    {#if okMsg}<p class="ok-msg">{okMsg}</p>{/if}

    {#if view === "logs"}
      <p class="sub">软岩、硬岩用两套合格闭区间，不是全线一个门槛。新单必须点选等级，漏选整份退回；认领时抄录当时该档上下限进快照。</p>
      {#if isWriter}
        <section>
          <h2>报收敛读数</h2>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>围岩等级（必选，点选口径与入库一致：soft=软岩，hard=硬岩）</label>
          <select bind:value={grade}>
            <option value="" disabled>— 请点选围岩等级 —</option>
            <option value="soft">软岩（soft）</option>
            <option value="hard">硬岩（hard）</option>
          </select>
          <label>收敛（毫米，可正可负，判定取绝对值）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading || !grade} on:click={submit}>提交（进入待认领）</button>
        </section>
      {:else}
        <section><h2>巡检员只读</h2><p class="block-hint">可翻表、可翻改档履历与认领快照，但不能改档，也不能报数。</p></section>
      {/if}
      <section>
        <h2>收敛单据表</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>围岩档</th><th>收敛mm</th><th>认领快照区间mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td>
                  {#if row.grade_label}
                    <span class="tag {row.grade === 'soft' ? 'grade-soft' : 'grade-hard'}">{row.grade_label}（{row.grade}）</span>
                  {:else}<span class="empty">未点选</span>{/if}
                </td>
                <td>{row.delta_mm}</td>
                <td class="mono">
                  {#if row.snap_lower_mm !== null && row.snap_upper_mm !== null}
                    [{fmt(row.snap_lower_mm)}, {fmt(row.snap_upper_mm)}]
                  {:else}
                    {row.status === "pending" ? "待认领时抄录" : "—"}
                  {/if}
                </td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === "pending" ? "待认领" : "已认领"}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if logs.length === 0}<p class="empty">还没有单据。</p>{/if}
      </section>
    {:else}
      <!-- ===== 围岩分带专页：上块填档位 / 中块改档履历 / 下块认领快照 ===== -->
      <p class="sub">软岩、硬岩各自维护合格闭区间；已领走的单据继续沿用领走那一刻抄进快照的上下限，改档不翻旧案。</p>

      <section>
        <h2>上块 · 填档位（当前合格闭区间）</h2>
        <p class="block-hint">
          {#if isWriter}
            测量员可分别设定软岩、硬岩的上下限（毫米，按收敛绝对值做闭区间判定，上下限本身算合格）；保存即追加改档履历。
          {:else}
            巡检员只能查看当前档位，不能改档。
          {/if}
        </p>
        <div class="grid2">
          {#each limits as l}
            <div class="card">
              <h3>{l.grade_label}（<span class="mono">{l.grade}</span>）</h3>
              {#if isWriter && drafts[l.grade]}
                <div class="row2">
                  <div>
                    <label>下限 mm（含）</label>
                    <input type="number" step="0.1" bind:value={drafts[l.grade].lower_mm} />
                  </div>
                  <div>
                    <label>上限 mm（含）</label>
                    <input type="number" step="0.1" bind:value={drafts[l.grade].upper_mm} />
                  </div>
                </div>
                <button on:click={() => saveLimit(l.grade)}>保存并记入履历</button>
              {:else}
                <p class="mono">合格闭区间：[{fmt(l.lower_mm)}, {fmt(l.upper_mm)}] mm</p>
              {/if}
              <p class="block-hint">最近更新：{l.updated_by} · {l.updated_at ? new Date(l.updated_at).toLocaleString() : "—"}</p>
            </div>
          {/each}
        </div>
        {#if limits.length === 0}<p class="empty">档位尚未加载。</p>{/if}
      </section>

      <section>
        <h2>中块 · 改档履历</h2>
        <p class="block-hint">每次改上下限追加一行，只增不改；巡检员可翻履历。</p>
        <table>
          <thead>
            <tr><th>时间</th><th>围岩档</th><th>旧闭区间mm</th><th>新闭区间mm</th><th>改档人</th></tr>
          </thead>
          <tbody>
            {#each history as h}
              <tr>
                <td>{h.changed_at ? new Date(h.changed_at).toLocaleString() : "—"}</td>
                <td><span class="tag {h.grade === 'soft' ? 'grade-soft' : 'grade-hard'}">{h.grade_label}（{h.grade}）</span></td>
                <td class="mono">[{fmt(h.old_lower_mm)}, {fmt(h.old_upper_mm)}]</td>
                <td class="mono">[{fmt(h.new_lower_mm)}, {fmt(h.new_upper_mm)}]</td>
                <td>{h.changed_by}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if history.length === 0}<p class="empty">尚无改档记录；档位仍为系统默认值。</p>{/if}
      </section>

      <section>
        <h2>下块 · 认领快照</h2>
        <p class="block-hint">单据被领走那一刻抄录的围岩档上下限；此后再改档，这些单据仍按快照判定。</p>
        <table>
          <thead>
            <tr><th>单据号</th><th>桩号</th><th>围岩档</th><th>收敛mm</th><th>快照闭区间mm</th><th>认领时间</th><th>结论</th></tr>
          </thead>
          <tbody>
            {#each logs.filter(r => r.snap_lower_mm !== null && r.snap_upper_mm !== null) as r}
              <tr>
                <td>{r.id}</td>
                <td>{r.chainage}</td>
                <td>{r.grade_label ?? "—"}</td>
                <td>{r.delta_mm}</td>
                <td class="mono">[{fmt(r.snap_lower_mm)}, {fmt(r.snap_upper_mm)}]</td>
                <td>{r.processed_at ? new Date(r.processed_at).toLocaleString() : "—"}</td>
                <td>{#if r.verdict}<span class="tag {r.verdict === '合格' ? 'ok' : 'bad'}">{r.verdict}</span>{:else}—{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if logs.filter(r => r.snap_lower_mm !== null && r.snap_upper_mm !== null).length === 0}
          <p class="empty">还没有任何单据被认领，暂无快照。</p>
        {/if}
      </section>
    {/if}
  {/if}
</main>
