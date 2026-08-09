import { Navigate, Route, Routes } from 'react-router-dom'
import { ParticipantProvider } from './ParticipantContext'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import EventRoute from './components/EventRoute'
import ParticipantLayout from './components/ParticipantLayout'
import CodingPage from './pages/CodingPage'
import DashboardPage from './pages/DashboardPage'
import JudgingWaitPage from './pages/JudgingWaitPage'
import LoginPage from './pages/LoginPage'
import ParticipantHomePage from './pages/ParticipantHomePage'
import ResultsPage from './pages/ResultsPage'
import RoundOneBiddingPage from './pages/RoundOneBiddingPage'
import RoundOnePreviewPage from './pages/RoundOnePreviewPage'
import RoundResultPage from './pages/RoundResultPage'
import SubmissionPage from './pages/SubmissionPage'
import WildcardApplicationPage from './pages/WildcardApplicationPage'
import WildcardBiddingPage from './pages/WildcardBiddingPage'
import WildcardPreviewPage from './pages/WildcardPreviewPage'
import WildcardSelectionPage from './pages/WildcardSelectionPage'

const eventPage = (state: Parameters<typeof EventRoute>[0]['state'], page: React.ReactNode) => (
  <EventRoute state={state}>{page}</EventRoute>
)

export default function ParticipantApp() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route path="" element={<ProtectedRoute><ParticipantProvider><ParticipantLayout /></ParticipantProvider></ProtectedRoute>}>
          <Route index element={<ParticipantHomePage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="problem" element={eventPage('ROUND1_PREVIEW', <RoundOnePreviewPage />)} />
          <Route path="bid" element={eventPage('ROUND1_BIDDING', <RoundOneBiddingPage />)} />
          <Route path="result" element={eventPage('ROUND1_RESULT', <RoundResultPage />)} />
          <Route path="wildcard" element={eventPage('WILDCARD_APPLICATION', <WildcardApplicationPage />)} />
          <Route path="wildcard/preview" element={eventPage('WILDCARD_PREVIEW', <WildcardPreviewPage />)} />
          <Route path="wildcard/bid" element={eventPage('WILDCARD_BIDDING', <WildcardBiddingPage />)} />
          <Route path="wildcard/select" element={eventPage('WILDCARD_SELECTION', <WildcardSelectionPage />)} />
          <Route path="coding" element={eventPage('CODING', <CodingPage />)} />
          <Route path="submission" element={eventPage('SUBMISSION', <SubmissionPage />)} />
          <Route path="judging" element={eventPage('JUDGING_WAIT', <JudgingWaitPage />)} />
          <Route path="results" element={eventPage('RESULTS', <ResultsPage />)} />
        </Route>
        <Route path="*" element={<Navigate to="/participant" replace />} />
      </Routes>
    </AuthProvider>
  )
}
