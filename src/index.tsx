import { PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaUserShield } from "react-icons/fa";
import { t } from "./i18n";
import { useStatus } from "./useStatus";
import { ConnectionSection } from "./sections/ConnectionSection";
import { KeysSection } from "./sections/KeysSection";
import { LoginSection } from "./sections/LoginSection";
import { ServiceSection } from "./sections/ServiceSection";
import { StatusSection } from "./sections/StatusSection";
import { TrustedSection } from "./sections/TrustedSection";

function Content() {
  const { status, error, refresh } = useStatus();

  if (!status) {
    return (
      <PanelSection>
        <PanelSectionRow>{error ? t.loadFailed(error) : t.loading}</PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <>
      <ServiceSection status={status} refresh={refresh} />
      <StatusSection status={status} />
      <ConnectionSection status={status} refresh={refresh} />
      <LoginSection status={status} refresh={refresh} />
      <KeysSection status={status} refresh={refresh} />
      <TrustedSection status={status} refresh={refresh} />
    </>
  );
}

export default definePlugin(() => ({
  name: "SSH Warden",
  titleView: <div className={staticClasses.Title}>SSH Warden</div>,
  content: <Content />,
  icon: <FaUserShield />,
}));
