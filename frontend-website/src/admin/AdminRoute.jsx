import StyleBoundary from '../shared/components/StyleBoundary'
import App from './App'
import appStyles from './App.css?inline'
import baseStyles from './index.css?inline'
import loginStyles from './pages/Login.css?inline'

export default function AdminRoute() {
  return (
    <StyleBoundary rootClassName="admin-root" styles={`${baseStyles}\n${appStyles}\n${loginStyles}`}>
      <App />
    </StyleBoundary>
  )
}
