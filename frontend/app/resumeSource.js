import {
  fetchInterviewResume,
  importDefaultInterviewResume,
  uploadInterviewResume,
} from "./api.js";

let resumeStatus = null;

export function setupResumeSourceControls() {
  const defaultButton = document.querySelector("[data-resume-source-import-default]");
  const uploadButton = document.querySelector("[data-resume-source-upload]");
  const fileInput = document.querySelector("[data-resume-source-file]");
  if (defaultButton) {
    defaultButton.addEventListener("click", () => {
      void importDefaultResume(defaultButton);
    });
  }
  if (uploadButton && fileInput) {
    uploadButton.addEventListener("click", () => {
      fileInput.click();
    });
    fileInput.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      if (file) {
        void uploadResume(file, uploadButton);
      }
      fileInput.value = "";
    });
  }
}

export async function refreshResumeStatus() {
  try {
    resumeStatus = await fetchInterviewResume();
  } catch (error) {
    setResumeStatus({ imported: false, title: "", chars: 0, error: error.message || "读取简历失败" });
  }
  renderResumeStatus();
}

export function renderResumeStatus() {
  const status = document.querySelector("[data-resume-source-status]");
  const badge = document.querySelector("[data-resume-source-badge]");
  const meta = document.querySelector("[data-resume-source-meta]");
  const card = document.querySelector(".resume-source-card");
  if (!status || !badge || !meta) {
    return;
  }
  card?.classList.toggle("is-connected", resumeStatus?.imported === true);
  if (!resumeStatus) {
    status.textContent = "正在读取简历状态...";
    badge.textContent = "未导入";
    meta.textContent = "";
    return;
  }
  if (resumeStatus.error) {
    status.textContent = resumeStatus.error;
    badge.textContent = "待处理";
    meta.textContent = "";
    return;
  }
  if (!resumeStatus.imported) {
    status.textContent = resumeStatus.default_exists
      ? "可从默认路径导入，也可以手动上传"
      : "可手动上传 PDF；默认路径暂未找到";
    badge.textContent = "未导入";
    meta.textContent = "";
    return;
  }
  status.textContent = resumeStatus.title || "已导入简历";
  badge.textContent = "已导入";
  meta.textContent = `${Number(resumeStatus.chars || 0)} chars`;
}

async function importDefaultResume(button) {
  button.disabled = true;
  setResumeStatus({ imported: false, title: "", chars: 0, error: "正在导入默认简历..." });
  try {
    resumeStatus = await importDefaultInterviewResume();
  } catch (error) {
    setResumeStatus({ imported: false, title: "", chars: 0, error: error.message || "导入失败" });
  } finally {
    button.disabled = false;
    renderResumeStatus();
  }
}

async function uploadResume(file, button) {
  button.disabled = true;
  setResumeStatus({ imported: false, title: file.name, chars: 0, error: "正在上传并解析..." });
  try {
    resumeStatus = await uploadInterviewResume(file);
  } catch (error) {
    setResumeStatus({ imported: false, title: file.name, chars: 0, error: error.message || "上传失败" });
  } finally {
    button.disabled = false;
    renderResumeStatus();
  }
}

function setResumeStatus(status) {
  resumeStatus = status;
  renderResumeStatus();
}
