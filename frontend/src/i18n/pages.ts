// The texts of the pages loaded on demand (it.pages.json), in their own block: every such page imports this file
// first, so its texts are in place before any of its modules runs (src/i18n/split.test.ts).
import { addTexts } from "./index";
import pages from "./it.pages.json";

addTexts(pages);
