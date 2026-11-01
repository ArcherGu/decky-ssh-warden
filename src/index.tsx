import { PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaUserShield } from "react-icons/fa";
import { useStatus } from "./useStatus";
import { StatusSection } from "./sections/StatusSection";

function Content() {
  const { status, error } = useStatus();

  if (!status) {
    return (
      <PanelSection>
        <PanelSectionRow>{error ? `读取状态失败：${error}` : "正在读取 SSH 状态…"}</PanelSectionRow>
      </PanelSection>
    );
  }

  return <StatusSection status={status} />;
}

export default definePlugin(() => ({
  name: "SSH Warden",
  titleView: <div className={staticClasses.Title}>SSH Warden</div>,
  content: <Content />,
  icon: <FaUserShield />,
}));
