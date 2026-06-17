const pageRoot = document.querySelector(".review-page");
const reviewerId = pageRoot.dataset.reviewerId || "";
const questionsEl = document.querySelector("#questions");
const errorBox = document.querySelector("#errorBox");
const statusFilter = document.querySelector("#statusFilter");
const pageSizeEl = document.querySelector("#pageSize");
const prevPage = document.querySelector("#prevPage");
const nextPage = document.querySelector("#nextPage");
const pageInfo = document.querySelector("#pageInfo");
const progressText = document.querySelector("#progressText");
const rangeLabel = document.querySelector("#rangeLabel");

let currentPage = 1;
let pageCount = 1;

const statusClass = {
  pending: "status-pending",
  keep: "status-keep",
  delete: "status-delete",
};

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderQuestion(question) {
  const card = document.createElement("article");
  card.className = "question-card";
  card.dataset.questionId = question.question_id;
  card.innerHTML = `
    <div class="question-head">
      <div>
        <strong>#${question.question_id}</strong>
        <span class="status ${statusClass[question.review_status] || ""}">
          ${escapeHtml(question.review_status_label)}
        </span>
      </div>
      <div class="question-meta">
        <span class="tag">${escapeHtml(question.subject_code)}</span>
        <span class="tag">${escapeHtml(question.subject_name)}</span>
        <span class="tag">${escapeHtml(question.question_type)}</span>
      </div>
    </div>
    <div class="question-content">${escapeHtml(question.content)}</div>
    <div class="question-actions">
      <button class="keep-button" type="button" data-action="keep">保留</button>
      <button class="delete-button" type="button" data-action="delete">删除</button>
    </div>
  `;
  return card;
}

function updatePagination(pagination) {
  currentPage = pagination.page;
  pageCount = pagination.page_count;
  pageInfo.textContent = `第 ${currentPage} / ${pageCount} 页，共 ${pagination.total} 道`;
  prevPage.disabled = currentPage <= 1;
  nextPage.disabled = currentPage >= pageCount;
}

async function refreshProgress() {
  if (!reviewerId) {
    progressText.textContent = "缺少 reviewer_id";
    return;
  }
  const response = await fetch(`/api/progress?reviewer_id=${encodeURIComponent(reviewerId)}`);
  const data = await response.json();
  if (!response.ok) {
    showError(data.error || "读取进度失败");
    return;
  }
  const item = data.reviewer;
  progressText.textContent = `已处理 ${item.reviewed} / 共 ${item.total}`;
}

async function loadQuestions() {
  clearError();
  if (!reviewerId) {
    showError("请通过 /review?reviewer_id=reviewer_1 这样的地址进入筛选页。");
    return;
  }

  const params = new URLSearchParams({
    reviewer_id: reviewerId,
    status: statusFilter.value,
    page: currentPage,
    page_size: pageSizeEl.value,
  });
  const response = await fetch(`/api/questions?${params.toString()}`);
  const data = await response.json();
  if (!response.ok) {
    showError(data.error || "读取题目失败");
    questionsEl.innerHTML = "";
    return;
  }

  const assignment = data.assignment;
  rangeLabel.textContent = `（${assignment.start_question_id}–${assignment.end_question_id}）`;
  questionsEl.innerHTML = "";
  if (data.questions.length === 0) {
    questionsEl.innerHTML = '<div class="message">当前条件下没有题目。</div>';
  } else {
    data.questions.forEach((question) => {
      questionsEl.appendChild(renderQuestion(question));
    });
  }
  updatePagination(data.pagination);
  await refreshProgress();
}

async function submitReview(card, action) {
  clearError();
  const buttons = card.querySelectorAll("button");
  buttons.forEach((button) => {
    button.disabled = true;
  });
  const questionId = Number(card.dataset.questionId);

  try {
    const response = await fetch("/api/review", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        reviewer_id: reviewerId,
        question_id: questionId,
        action,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      showError(data.error || "保存失败");
      return;
    }
    const statusEl = card.querySelector(".status");
    statusEl.textContent = data.review_status_label;
    statusEl.className = `status ${statusClass[data.review_status] || ""}`;
    await refreshProgress();
    if (statusFilter.value !== "all" && statusFilter.value !== data.review_status) {
      card.remove();
    }
  } finally {
    buttons.forEach((button) => {
      button.disabled = false;
    });
  }
}

questionsEl.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const card = button.closest(".question-card");
  submitReview(card, button.dataset.action);
});

statusFilter.addEventListener("change", () => {
  currentPage = 1;
  loadQuestions();
});

pageSizeEl.addEventListener("change", () => {
  currentPage = 1;
  loadQuestions();
});

prevPage.addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage -= 1;
    loadQuestions();
  }
});

nextPage.addEventListener("click", () => {
  if (currentPage < pageCount) {
    currentPage += 1;
    loadQuestions();
  }
});

loadQuestions();
