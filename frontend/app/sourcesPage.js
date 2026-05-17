import {
  refreshResumeStatus,
  renderResumeStatus,
  setupResumeSourceControls,
} from "./resumeSource.js";
import {
  refreshSourcePlatforms,
  renderSourcePlatformStatus,
  setupSourcePlatformControls,
} from "./sourcePlatforms.js";

export function setupSourcesPage() {
  setupResumeSourceControls();
  setupSourcePlatformControls();
  renderResumeStatus();
  void refreshResumeStatus();
  renderSourcePlatformStatus();
  void refreshSourcePlatforms();
}
