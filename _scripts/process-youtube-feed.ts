import { readTXT, removeFile } from "https://deno.land/x/flat@0.0.15/mod.ts";
import { DOMParser } from "https://deno.land/x/deno_dom@v0.1.38/deno-dom-wasm.ts";

const filename = Deno.args[0];
const xmlText = await readTXT(filename);

const doc = new DOMParser().parseFromString(xmlText, "text/xml");
if (!doc) {
  console.error("Failed to parse XML feed");
  Deno.exit(1);
}

const entries = doc.getElementsByTagName("entry");

for (const entry of entries) {
  const videoId =
    entry.getElementsByTagName("yt:videoId")[0]?.textContent?.trim();
  const title = entry.getElementsByTagName("title")[0]?.textContent?.trim();
  const published =
    entry.getElementsByTagName("published")[0]?.textContent?.trim();

  const mediaGroup = entry.getElementsByTagName("media:group")[0];
  const description =
    mediaGroup
      ?.getElementsByTagName("media:description")[0]
      ?.textContent?.trim() ?? "";

  if (!videoId || !title || !published) {
    console.log("Skipping entry with missing data");
    continue;
  }

  const slug = generateSlug(title);
  const filePath = `_hospitality-talks/${slug}.md`;

  let fileExists = false;
  try {
    await Deno.stat(filePath);
    fileExists = true;
  } catch {
    fileExists = false;
  }

  if (fileExists) {
    console.log(`Skipped (already exists): ${filePath}`);
    continue;
  }

  const formattedDate = formatDate(published);
  const escapedTitle = title.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const indentedDescription = description.replace(/\n/g, "\n  ");

  const content = `---
title: "${escapedTitle}"
description: |
  ${indentedDescription}
video: https://youtu.be/${videoId}
date: ${formattedDate}
---
`;

  await Deno.writeTextFile(filePath, content);
  console.log(`Created: ${filePath}`);
}

await removeFile(filename);
console.log("Removed raw feed file");

function generateSlug(title: string): string {
  return title
    .toLowerCase()
    .replace(/['']/g, "-s")
    .replace(/[&]/g, "")
    .replace(/[–—]/g, "")
    .replace(/[?.,!:;""()]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function formatDate(isoDate: string): string {
  const d = new Date(isoDate);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day} 00:00:00 -0500`;
}
