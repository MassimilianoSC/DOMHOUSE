// Addresses shared by pages that live in different blocks (P-20): kept here so a page in the main block can link to a
// lazy page without importing it.

/** Value of ?appartamenti= that opens Organizzazioni with that organization's apartments already shown (D-77). */
export const OPEN_APARTMENTS_PARAM = "appartamenti";
export const platformApartmentsUrl = (tenantId: string) => `/organizzazioni?${OPEN_APARTMENTS_PARAM}=${encodeURIComponent(tenantId)}`;
