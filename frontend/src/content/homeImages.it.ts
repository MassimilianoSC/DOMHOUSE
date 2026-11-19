/** Local editorial backdrops; Unsplash author/source details stay here for traceability. */
const LANDSCAPE_SIZE = { width: 1280, height: 720 } as const;

export const HOME_IMAGES = [
  { src: "/images/home/domhouse-welcome.webp", credit: "Generata per DOMHOUSE", width: 1536, height: 1024 },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-02.webp", credit: "EZcurtain Life", source: "https://unsplash.com/photos/cozy-living-room-with-neutral-tones-and-natural-light-srzKmNLovaQ" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-03.webp", credit: "Brian Zajac", source: "https://unsplash.com/photos/modern-living-room-with-neutral-tones-and-natural-elements-tPz3Lhh3z_4" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-04.webp", credit: "Kamilla Isalieva", source: "https://unsplash.com/photos/cozy-living-room-with-modern-furniture-and-warm-lighting-FF34Xzvb3oc" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-05.webp", credit: "Zahraa Hassan", source: "https://unsplash.com/photos/sunlight-streams-into-a-cozy-room-with-plants-vFYK8li2V_s" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-06.webp", credit: "Luis Redondo", source: "https://unsplash.com/photos/a-cozy-living-room-with-natural-lighting-8Tj2HrEWZxc" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-07.webp", credit: "Sidath Vimukthi", source: "https://unsplash.com/photos/a-comfortable-bedroom-with-bed-and-lamp-EbnBI09AegA" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-08.webp", credit: "Olivier Collet", source: "https://unsplash.com/photos/a-modern-living-room-with-chairs-and-plants-RM6ZxX9UyjQ" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-09.webp", credit: "Andrea Davis", source: "https://unsplash.com/photos/a-bed-with-a-white-bed-spread-ll55zEQPWxQ" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-10.webp", credit: "tommao wang", source: "https://unsplash.com/photos/a-shelf-filled-with-lots-of-potted-plants-ElCq1SMs4Ww" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-11.webp", credit: "insung yoon", source: "https://unsplash.com/photos/modern-white-hallway-with-potted-plant-and-doorway-CPnokDJKTNs" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-12.webp", credit: "Venrick Azcueta", source: "https://unsplash.com/photos/a-cozy-living-room-with-white-walls-and-fireplace-WroXAWn1lME" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-13.webp", credit: "Clay Banks", source: "https://unsplash.com/photos/a-bed-sitting-in-a-bedroom-next-to-two-windows-_sdO0PgdgFw" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-14.webp", credit: "Rosalind Chang", source: "https://unsplash.com/photos/open-door-inside-house-_Kf-6OWPr9Y" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-15.webp", credit: "Vahe Ohanian", source: "https://unsplash.com/photos/a-patio-with-tables-and-chairs-mFNquCeExQs" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-16.webp", credit: "Sir. Simo", source: "https://unsplash.com/photos/patio-with-table-and-potted-plants-A-d-xu6OCBM" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-17.webp", credit: "qui nguyen", source: "https://unsplash.com/photos/garden-patio-with-two-chairs-lush-plants-and-warm-lighting-fVRSm1R5U_Q" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-18.webp", credit: "Josias Ubiera", source: "https://unsplash.com/photos/two-chairs-and-a-table-on-a-patio-hHypgEaIGsM" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-19.webp", credit: "Datingjungle", source: "https://unsplash.com/photos/a-patio-with-a-table-and-chairs-and-an-umbrella-KHJ2aB75gKk" },
  { ...LANDSCAPE_SIZE, src: "/images/home/home-20.webp", credit: "Sara Abilova", source: "https://unsplash.com/photos/a-patio-with-tables-and-chairs-and-umbrella-slVe9XcpGBE" },
] as const;

export const HOME_IMAGE_ROTATION_MS = 30 * 60 * 1000;
