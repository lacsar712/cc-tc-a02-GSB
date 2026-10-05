<script>
  let session = null;
  let logs = [];
  let zones = [];
  let history = [];
  let page = "logs"; // logs | zones
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let gradeKey = ""; // 新单必须点选，漏选整份退回
  let error = "";
  let loading = false;
  let timer;
  // 改档草稿：{ [grade]: { lower, upper, saving, err, ok } }
  let drafts = {};

  $: isWriter = session?.role === "writer";

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  function gradeLabel(key) {
    return zones.find((z) => z.grade === key)?.label || key;
  }

  async function refreshLogs() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
  }

  async function refreshZones() {
    if (!session) return;
    const res = await fetch("/api/zones", { headers: headers() });
    if (res.ok) zones = await res.json();
  }

  async function refreshHistory() {
    if (!session) return;
    const res = await fetch("/api/zones/history", { headers: headers() });
    if (res.ok) history = await res.json();
  }

  async function refreshAll() {
    await refreshLogs();
    await Promise.all([refreshZones(), refreshHistory()]);
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
      await refreshAll();
      timer = setInterval(refreshLogs, 2000);
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
    zones = [];
    history = [];
    page = "logs";
    localStorage.removeItem("tunnel_session");
  }

  async function switchPage(p) {
    page = p;
    error = "";
    if (p === "zones") await Promise.all([refreshZones(), refreshHistory()]);
  }

  async function submit() {
    error = "";
    // 前端先卡一道：等级必须点选；选项口径来自 /api/zones，与入库同一字典
    if (!gradeKey) {
      error = "新单必须点选围岩等级，漏选整份退回";
      return;
    }
    if (chainage.trim() === "") {
      error = "桩号不能为空";
      return;
    }
    if (deltaMm === "") {
      error = "收敛值不能为空";
      return;
    }
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        // rock_grade 直接传档位字典 key，点选与入库同一口径
        body: JSON.stringify({
          chainage,
          delta_mm: Number(deltaMm),
          rock_grade: gradeKey,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      gradeKey = "";
      await refreshLogs();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function startEdit(zone) {
    drafts = {
      ...drafts,
      [zone.grade]: {
        lower: String(zone.lower_limit_mm),
        upper: String(zone.upper_limit_mm),
        err: "",
        ok: "",
      },
    };
  }

  function patchDraft(grade, patch) {
    drafts = { ...drafts, [grade]: { ...drafts[grade], ...patch } };
  }

  function cancelEdit(grade) {
    const next = { ...drafts };
    delete next[grade];
    drafts = next;
  }

  async function saveZone(zone) {
    const d = drafts[zone.grade];
    if (!d) return;
    const lower = Number(d.lower);
    const upper = Number(d.upper);
    if (d.lower.trim() === "" || d.upper.trim() === "" || Number.isNaN(lower) || Number.isNaN(upper)) {
      patchDraft(zone.grade, { err: "上下限必须是数字", ok: "" });
      return;
    }
    if (lower > upper) {
      patchDraft(zone.grade, { err: "下限不能大于上限", ok: "" });
      return;
    }
    patchDraft(zone.grade, { err: "", ok: "" });
    try {
      const res = await fetch(`/api/zones/${zone.grade}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ lower_limit_mm: lower, upper_limit_mm: upper }),
      });
      const data = await res.json();
      if (!res.ok) {
        patchDraft(zone.grade, { err: data.detail || "改档失败", ok: "" });
        return;
      }
      drafts = { ...drafts, [zone.grade]: undefined };
      await Promise.all([refreshZones(), refreshHistory(), refreshLogs()]);
    } catch {
      patchDraft(zone.grade, { err: "改档时网络异常", ok: "" });
    }
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refreshAll();
      timer = setInterval(refreshLogs, 2000);
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
  header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem; }
  h1 { color: #fbbf24; margin: 0; font-size: 1.35rem; }
  nav { display: flex; gap: 0.5rem; }
  nav button { background: #44403c; color: #d6d3d1; }
  nav button.active { background: #d97706; color: #fff; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  h2 { font-size: 1rem; margin: 0 0 0.25rem; color: #fbbf24; }
  h3 { font-size: 0.95rem; margin: 0 0 0.6rem; color: #fde68a; }
  .block-note { color: #a8a29e; font-size: 0.82rem; margin: 0 0 0.75rem; }
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
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .err { color: #fb7185; }
  .ok-msg { color: #86efac; font-size: 0.82rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .grade-tag { background: #1e3a5f; color: #bfdbfe; }
  .zone-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 0.75rem; }
  .zone-card { border: 1px solid #57534e; border-radius: 6px; padding: 0.75rem 0.9rem; background: #1f1b19; }
  .zone-card .limits { font-size: 0.9rem; margin: 0.35rem 0; }
  .zone-card .meta { color: #a8a29e; font-size: 0.76rem; }
  .inline-inputs { display: flex; gap: 0.5rem; align-items: center; margin: 0.4rem 0; }
  .inline-inputs input { margin: 0; }
  .mono { font-variant-numeric: tabular-nums; }
</style>

<main>
  {#if !session}
    <h1>隧道收敛测缝台</h1>
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。软岩、硬岩各有一套合格闭区间。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <header>
      <h1>隧道收敛测缝台</h1>
      <nav>
        <button class={page === "logs" ? "active" : ""} on:click={() => switchPage("logs")}>收敛单据</button>
        <button class={page === "zones" ? "active" : ""} on:click={() => switchPage("zones")}>围岩分带</button>
      </nav>
    </header>
    <p class="sub">已登录：{session.username}（{isWriter ? "测量员·可改档/可报数" : "巡检员·只能翻表和履历，不能改档也不能报数"}）　<button class="secondary" on:click={logout}>退出</button></p>

    {#if page === "logs"}
      {#if isWriter}
        <section>
          <h2>新单</h2>
          <p class="block-note">围岩等级必须点选，漏选整份退回；点选口径与入库口径同为档位字典 key。</p>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>围岩等级（必选）</label>
          <select bind:value={gradeKey}>
            <option value="" disabled>— 请点选围岩等级 —</option>
            {#each zones as z}
              <option value={z.grade}>{z.label}（合格闭区间 [{z.lower_limit_mm}, {z.upper_limit_mm}] mm）</option>
            {/each}
          </select>
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
        </section>
      {/if}
      <section>
        <h2>收敛单据</h2>
        <button class="secondary" disabled={loading} on:click={refreshLogs}>刷新列表</button>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>等级</th><th>收敛mm</th><th>状态</th><th>结论</th><th>认领快照区间mm</th><th>说明</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td><span class="tag grade-tag">{row.rock_grade_label}</span></td>
                <td class="mono">{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td class="mono">
                  {#if row.lower_limit_mm != null && row.upper_limit_mm != null}
                    [{row.lower_limit_mm}, {row.upper_limit_mm}]
                  {:else}
                    <span class="block-note">待认领时抄写</span>
                  {/if}
                </td>
                <td>{row.reason ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <!-- ===== 围岩分带专页：上块档位 / 中块履历 / 下块认领快照 ===== -->
      <section>
        <h2>上块 · 当前档位（合格闭区间）</h2>
        <p class="block-note">软岩、硬岩各用一套闭区间，不设全线统一门槛；端点闭区间，lower ≤ 读数 ≤ upper 判合格。</p>
        <div class="zone-grid">
          {#each zones as z}
            <div class="zone-card">
              <h3>{z.label} <span class="block-note">（口径 key：{z.grade}）</span></h3>
              <p class="limits mono">现行闭区间：[{z.lower_limit_mm}, {z.upper_limit_mm}] mm</p>
              <p class="meta">最后改档：{z.updated_by} · {z.updated_at ? new Date(z.updated_at).toLocaleString() : "—"}</p>
              {#if isWriter}
                {#if drafts[z.grade]}
                  <div class="inline-inputs">
                    <input type="number" step="0.1" placeholder="下限" value={drafts[z.grade].lower}
                      on:input={(e) => patchDraft(z.grade, { lower: e.target.value })} />
                    <span>～</span>
                    <input type="number" step="0.1" placeholder="上限" value={drafts[z.grade].upper}
                      on:input={(e) => patchDraft(z.grade, { upper: e.target.value })} />
                  </div>
                  <button on:click={() => saveZone(z)}>确认改档</button>
                  <button class="secondary" on:click={() => cancelEdit(z.grade)}>取消</button>
                  {#if drafts[z.grade]?.err}<p class="err">{drafts[z.grade].err}</p>{/if}
                {:else}
                  <button class="secondary" on:click={() => startEdit(z)}>修改上下限</button>
                {/if}
              {:else}
                <p class="block-note">巡检员只读：可翻表、翻履历，不能改档。</p>
              {/if}
            </div>
          {/each}
        </div>
      </section>

      <section>
        <h2>中块 · 改档履历</h2>
        <p class="block-note">上下限每改一次留一条；改档只影响改档之后认领的单据。</p>
        <button class="secondary" on:click={refreshHistory}>刷新履历</button>
        <table>
          <thead>
            <tr><th>#</th><th>等级</th><th>旧闭区间mm</th><th>新闭区间mm</th><th>改档人</th><th>时间</th></tr>
          </thead>
          <tbody>
            {#each history as h}
              <tr>
                <td>{h.id}</td>
                <td><span class="tag grade-tag">{gradeLabel(h.grade)}</span></td>
                <td class="mono">[{h.old_lower_mm}, {h.old_upper_mm}]</td>
                <td class="mono">[{h.new_lower_mm}, {h.new_upper_mm}]</td>
                <td>{h.changed_by}</td>
                <td>{new Date(h.changed_at).toLocaleString()}</td>
              </tr>
            {:else}
              <tr><td colspan="6" class="block-note">暂无改档记录（当前均为系统初始档位）。</td></tr>
            {/each}
          </tbody>
        </table>
      </section>

      <section>
        <h2>下块 · 认领快照</h2>
        <p class="block-note">
          判定吃认领那一刻的当前闭区间：单据被领走时把当时的上下限抄进快照，之后阈值再改，
          已领走的单据继续沿用快照上下限，绝不改判；待认领单据将在认领时抄写新阈值。
        </p>
        <button class="secondary" on:click={refreshLogs}>刷新快照</button>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>等级</th><th>收敛mm</th><th>认领快照区间mm</th><th>结论</th><th>认领时间</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td><span class="tag grade-tag">{row.rock_grade_label}</span></td>
                <td class="mono">{row.delta_mm}</td>
                <td class="mono">
                  {#if row.lower_limit_mm != null && row.upper_limit_mm != null}
                    [{row.lower_limit_mm}, {row.upper_limit_mm}]
                  {:else}
                    <span class="block-note">待认领（尚未抄快照）</span>
                  {/if}
                </td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.processed_at ? new Date(row.processed_at).toLocaleString() : "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}
  {/if}
</main>
