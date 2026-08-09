import { Navigate, Route, Routes } from 'react-router-dom'
import { ParticipantProvider } from './participant/ParticipantContext'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './auth/ProtectedRoute'
import EventRoute from './participant/components/EventRoute'
import ParticipantLayout from './participant/components/ParticipantLayout'
import CodingPage from './participant/pages/CodingPage'
import DashboardPage from './participant/pages/DashboardPage'
import JudgingWaitPage from './participant/pages/JudgingWaitPage'
import LoginPage from './participant/pages/LoginPage'
import ParticipantHomePage from './participant/pages/ParticipantHomePage'
import ResultsPage from './participant/pages/ResultsPage'
import RoundOneBiddingPage from './participant/pages/RoundOneBiddingPage'
import RoundOnePreviewPage from './participant/pages/RoundOnePreviewPage'
import RoundResultPage from './participant/pages/RoundResultPage'
import SubmissionPage from './participant/pages/SubmissionPage'
import WildcardApplicationPage from './participant/pages/WildcardApplicationPage'
import WildcardBiddingPage from './participant/pages/WildcardBiddingPage'
import WildcardPreviewPage from './participant/pages/WildcardPreviewPage'
import WildcardSelectionPage from './participant/pages/WildcardSelectionPage'

const eventPage = (state: Parameters<typeof EventRoute>[0]['state'], page: React.ReactNode) => (
  <EventRoute state={state}>{page}</EventRoute>
)

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<ProtectedRoute><ParticipantProvider><ParticipantLayout /></ParticipantProvider></ProtectedRoute>}>
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
