import { PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaUserShield } from "react-icons/fa";
import { useStatus } from "./useStatus";
import { ConnectionSection } from "./sections/ConnectionSection";
import { LoginSection } from "./sections/LoginSection";
import { ServiceSection } from "./sections/ServiceSection";
import { StatusSection } from "./sections/StatusSection";

function Content() {
  const { status, error, refresh } = useStatus();

  if (!status) {
    return (
      <PanelSection>
        <PanelSectionRow>{error ? `读取状态失败：${error}` : "正在读取 SSH 状态…"}</PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <>
      <ServiceSection status={status} refresh={refresh} />
      <StatusSection status={status} />
      <ConnectionSection status={status} refresh={refresh} />
      <LoginSection status={status} refresh={refresh} />
    </>
  );
}

export default definePlugin(() => ({
  name: "SSH Warden",
  titleView: <div className={staticClasses.Title}>SSH Warden</div>,
  content: <Content />,
  icon: <FaUserShield />,
}));
