import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate';

export interface ZipEntryInfo {
  name: string;
  compressedSize: number;
  uncompressedSize: number;
  compressionMethod: number;
  localHeaderOffset: number;
  isDirectory: boolean;
}

export interface ZipInspection {
  entries: ZipEntryInfo[];
  fileNames: string[];
}

interface ZipFileContent {
  name: string;
  data: Uint8Array;
}

const normalizeZipPath = (value: string) => value.replace(/\\/g, '/').replace(/^\.\//, '').replace(/^\/+/, '');

const readZipEntries = async (file: File) => {
  const bytes = new Uint8Array(await file.arrayBuffer());
  return unzipSync(bytes);
};

export const inspectZipFile = async (file: File): Promise<ZipInspection> => {
  const unzipped = await readZipEntries(file);
  const entries = Object.entries(unzipped).map(([name, data]) => {
    const normalizedName = normalizeZipPath(name);
    return {
      name: normalizedName,
      compressedSize: data.byteLength,
      uncompressedSize: data.byteLength,
      compressionMethod: 0,
      localHeaderOffset: 0,
      isDirectory: normalizedName.endsWith('/'),
    };
  });

  return {
    entries,
    fileNames: entries.map((entry) => entry.name),
  };
};

export const readZipEntryText = async (file: File, entryName: string) => {
  const normalizedEntryName = normalizeZipPath(entryName);
  const unzipped = await readZipEntries(file);
  const match = Object.entries(unzipped).find(([name]) => normalizeZipPath(name) === normalizedEntryName);
  if (!match) {
    throw new Error(`Entry point ${entryName} was not found in source.zip.`);
  }

  return strFromU8(match[1]);
};

export const buildStoredZip = (files: ZipFileContent[], filename = 'source.zip') => {
  const zipInput = files.reduce<Record<string, Uint8Array>>((current, file) => {
    current[normalizeZipPath(file.name)] = file.data;
    return current;
  }, {});
  const zipped = zipSync(zipInput, { level: 0 });
  return new File([zipped.buffer as ArrayBuffer], filename, { type: 'application/zip' });
};

export const rebuildZipWithEditedEntry = async (file: File, entryName: string, text: string) => {
  const normalizedEntryName = normalizeZipPath(entryName);
  const unzipped = await readZipEntries(file);
  const match = Object.keys(unzipped).find((name) => normalizeZipPath(name) === normalizedEntryName);
  if (!match) {
    throw new Error(`Cannot rebuild zip: ${entryName} was not found.`);
  }

  unzipped[match] = strToU8(text);
  const zipped = zipSync(unzipped, { level: 0 });
  return new File([zipped.buffer as ArrayBuffer], file.name || 'source.zip', { type: 'application/zip' });
};

export const downloadFile = (file: File) => {
  const url = URL.createObjectURL(file);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file.name;
  anchor.click();
  URL.revokeObjectURL(url);
};
