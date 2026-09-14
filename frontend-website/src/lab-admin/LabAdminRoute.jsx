import StyleBoundary from "../shared/components/StyleBoundary";
import LabAdminApp from "./LabAdminApp";
import appStyles from "../admin/App.css?inline";
import baseStyles from "../admin/index.css?inline";
import loginStyles from "../admin/pages/Login.css?inline";
import labStyles from "../labs/LabAllocationPanel.css?inline";
import routeStyles from "./lab-admin.css?inline";

export default function LabAdminRoute() {
  return <StyleBoundary rootClassName="admin-root" styles={`${baseStyles}\n${appStyles}\n${loginStyles}\n${labStyles}\n${routeStyles}`}><LabAdminApp /></StyleBoundary>;
}
