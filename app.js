const elements = {
  candidateCount: document.querySelector("#candidate-count"),
  voteCount: document.querySelector("#vote-count"),
  auditStatus: document.querySelector("#audit-status"),
  auditDetail: document.querySelector("#audit-detail"),
  candidateList: document.querySelector("#candidate-list"),
  candidateForm: document.querySelector("#candidate-form"),
  candidateName: document.querySelector("#candidate-name"),
  candidateParty: document.querySelector("#candidate-party"),
  voteCandidate: document.querySelector("#vote-candidate"),
  voterToken: document.querySelector("#voter-token"),
  voteForm: document.querySelector("#vote-form"),
  receipt: document.querySelector("#vote-receipt"),
  issueTokenButton: document.querySelector("#issue-token-button"),
  refreshButton: document.querySelector("#refresh-button"),
  ledgerBadge: document.querySelector("#ledger-badge"),
  ledgerRows: document.querySelector("#ledger-rows"),
  ledgerTotal: document.querySelector("#ledger-total"),
  resultsList: document.querySelector("#results-list"),
  resultsTotal: document.querySelector("#results-total"),
  lastUpdated: document.querySelector("#last-updated"),
  toast: document.querySelector("#toast"),
};

let toastTimer;

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `Erro ${response.status}`;
    throw new Error(detail);
  }
  return data;
}

function notify(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => elements.toast.classList.remove("visible"), 3600);
}

function initials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] || "")
    .join("")
    .toLocaleUpperCase("pt");
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function pluralize(count, singular, plural) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function renderCandidates(candidates) {
  elements.candidateCount.textContent = String(candidates.length);
  const selectedId = elements.voteCandidate.value;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = candidates.length ? "Selecione um candidato" : "Cadastre um candidato primeiro";
  elements.voteCandidate.replaceChildren(placeholder);

  for (const candidate of candidates) {
    const option = document.createElement("option");
    option.value = candidate.candidate_id;
    option.textContent = candidate.party ? `${candidate.name} · ${candidate.party}` : candidate.name;
    elements.voteCandidate.append(option);
  }
  if (candidates.some((candidate) => candidate.candidate_id === selectedId)) {
    elements.voteCandidate.value = selectedId;
  }
  elements.voteCandidate.disabled = candidates.length === 0;

  if (!candidates.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Ainda não há candidatos. Adicione o primeiro acima.";
    elements.candidateList.replaceChildren(empty);
    return;
  }

  const fragment = document.createDocumentFragment();
  candidates.forEach((candidate, index) => {
    const item = document.createElement("article");
    item.className = "candidate-item";
    const avatar = document.createElement("span");
    avatar.className = "candidate-avatar";
    avatar.textContent = initials(candidate.name);
    const copy = document.createElement("div");
    copy.className = "candidate-item-copy";
    const name = document.createElement("div");
    name.className = "candidate-item-name";
    name.textContent = candidate.name;
    const party = document.createElement("div");
    party.className = "candidate-item-party";
    party.textContent = candidate.party || "Independente";
    const number = document.createElement("span");
    number.className = "candidate-number";
    number.textContent = String(index + 1).padStart(2, "0");
    copy.append(name, party);
    item.append(avatar, copy, number);
    fragment.append(item);
  });
  elements.candidateList.replaceChildren(fragment);
}

function renderResults(data) {
  elements.voteCount.textContent = String(data.ballots_count);
  elements.resultsTotal.textContent = String(data.ballots_count);
  if (!data.results.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Cadastre candidatos para começar a simulação.";
    elements.resultsList.replaceChildren(empty);
    return;
  }

  const maxVotes = Math.max(1, ...data.results.map((candidate) => candidate.votes));
  const fragment = document.createDocumentFragment();
  for (const candidate of data.results) {
    const row = document.createElement("div");
    row.className = "result-row";
    const label = document.createElement("div");
    label.className = "result-label";
    const name = document.createElement("span");
    name.textContent = candidate.name;
    const votes = document.createElement("strong");
    votes.textContent = pluralize(candidate.votes, "voto", "votos");
    const track = document.createElement("div");
    track.className = "result-track";
    track.setAttribute("aria-label", `${candidate.name}: ${candidate.votes} votos`);
    const bar = document.createElement("div");
    bar.className = "result-bar";
    bar.style.width = `${(candidate.votes / maxVotes) * 100}%`;
    track.append(bar);
    label.append(name, votes);
    row.append(label, track);
    fragment.append(row);
  }
  elements.resultsList.replaceChildren(fragment);
}

function renderAudit(data) {
  const hasBlocks = data.blocks > 0;
  const verified = data.chain_valid;
  elements.auditStatus.textContent = !hasBlocks ? "Aguardando" : verified ? "Íntegro" : "Atenção";
  elements.auditDetail.textContent = !hasBlocks
    ? "Ainda sem votos para verificar"
    : verified
      ? `${data.blocks} ${data.blocks === 1 ? "bloco verificado" : "blocos verificados"}`
      : "Foi detetada uma inconsistência";
  elements.ledgerBadge.textContent = !hasBlocks ? "À espera de votos" : verified ? "Cadeia verificada" : "Verificação falhou";
  elements.ledgerBadge.className = `status-badge ${!hasBlocks ? "status-neutral" : verified ? "status-good" : "status-bad"}`;
  elements.ledgerTotal.textContent = pluralize(data.blocks, "bloco", "blocos");

  if (!data.records.length) {
    const empty = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "table-empty";
    cell.textContent = "O ledger aparecerá aqui depois do primeiro voto.";
    empty.append(cell);
    elements.ledgerRows.replaceChildren(empty);
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const record of [...data.records].reverse().slice(0, 6)) {
    const row = document.createElement("tr");
    const sequence = document.createElement("td");
    sequence.textContent = `#${String(record.sequence).padStart(4, "0")}`;
    const date = document.createElement("td");
    date.textContent = formatDate(record.created_at);
    const hash = document.createElement("td");
    hash.className = "hash-cell";
    hash.textContent = `${record.block_hash.slice(0, 18)}…`;
    hash.title = record.block_hash;
    const verification = document.createElement("td");
    verification.className = `verification${record.valid ? "" : " invalid"}`;
    verification.textContent = record.valid ? "Assinatura válida" : "Inválido";
    row.append(sequence, date, hash, verification);
    fragment.append(row);
  }
  elements.ledgerRows.replaceChildren(fragment);
}

async function refreshDashboard(showToast = false) {
  elements.refreshButton.disabled = true;
  try {
    const [candidates, audit] = await Promise.all([
      request("/candidates"),
      request("/audit/ledger"),
    ]);
    renderCandidates(candidates);
    renderAudit(audit);
    elements.voteCount.textContent = String(audit.blocks);
    if (!audit.chain_valid) {
      elements.resultsList.replaceChildren();
      const warning = document.createElement("p");
      warning.className = "empty-state";
      warning.textContent = "Apuração bloqueada: corrija a inconsistência detetada no ledger.";
      elements.resultsList.append(warning);
      elements.resultsTotal.textContent = "—";
      elements.lastUpdated.textContent = "Auditoria falhou. A apuração está bloqueada.";
      notify("Foi detetada uma inconsistência. A apuração foi bloqueada.", true);
      return;
    }
    const tally = await request("/tally");
    renderResults(tally);
    elements.lastUpdated.textContent = `Atualizado às ${new Intl.DateTimeFormat("pt", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date())} · atualização automática`;
    if (showToast) notify("Painel atualizado.");
  } catch (error) {
    notify(`Não foi possível atualizar os dados: ${error.message}`, true);
    elements.lastUpdated.textContent = "Falha ao atualizar. Tente novamente.";
  } finally {
    elements.refreshButton.disabled = false;
  }
}

elements.candidateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = elements.candidateForm.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await request("/candidates", {
      method: "POST",
      body: JSON.stringify({
        name: elements.candidateName.value.trim(),
        party: elements.candidateParty.value.trim() || null,
      }),
    });
    elements.candidateForm.reset();
    notify("Candidato adicionado.");
    await refreshDashboard();
  } catch (error) {
    notify(`Não foi possível adicionar o candidato: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

elements.issueTokenButton.addEventListener("click", async () => {
  elements.issueTokenButton.disabled = true;
  try {
    const result = await request("/voters/demo-token", { method: "POST" });
    elements.voterToken.value = result.voter_token;
    elements.voterToken.focus();
    notify("Token de teste emitido. Use-o uma vez para votar.");
  } catch (error) {
    notify(`Não foi possível emitir o token: ${error.message}`, true);
  } finally {
    elements.issueTokenButton.disabled = false;
  }
});

elements.voteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = elements.voteForm.querySelector('button[type="submit"]');
  button.disabled = true;
  elements.receipt.hidden = true;
  try {
    const receipt = await request("/votes", {
      method: "POST",
      body: JSON.stringify({
        candidate_id: elements.voteCandidate.value,
        voter_token: elements.voterToken.value.trim(),
      }),
    });
    elements.voterToken.value = "";
    elements.receipt.replaceChildren();
    const summary = document.createElement("strong");
    summary.textContent = `Voto cifrado e registado no bloco #${String(receipt.sequence).padStart(4, "0")}.`;
    const hash = document.createElement("span");
    hash.className = "receipt-hash";
    hash.textContent = `Hash: ${receipt.block_hash}`;
    elements.receipt.append(summary, hash);
    elements.receipt.hidden = false;
    notify("Voto registado. O ledger foi atualizado.");
    await refreshDashboard();
  } catch (error) {
    notify(`Não foi possível registar o voto: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

elements.refreshButton.addEventListener("click", () => refreshDashboard(true));

refreshDashboard();
window.setInterval(() => refreshDashboard(), 15000);
