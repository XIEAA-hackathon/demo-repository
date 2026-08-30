const TOKEN_KEY = 'bid_to_build_participant_token'

export const getAccessToken = () => localStorage.getItem(TOKEN_KEY)
export const setAccessToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const clearAccessToken = () => localStorage.removeItem(TOKEN_KEY)
