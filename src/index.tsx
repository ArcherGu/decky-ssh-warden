import { PanelSection, PanelSectionRow, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaUserShield } from "react-icons/fa";

function Content() {
  return (
    <PanelSection>
      <PanelSectionRow>SSH Warden</PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "SSH Warden",
  titleView: <div className={staticClasses.Title}>SSH Warden</div>,
  content: <Content />,
  icon: <FaUserShield />,
}));
