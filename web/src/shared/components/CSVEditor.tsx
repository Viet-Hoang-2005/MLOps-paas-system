import { useState, useEffect, useMemo } from 'react';
import Papa from 'papaparse';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface CSVEditorProps {
  initialCsvText: string;
  onChange?: (csvText: string) => void;
  readOnly?: boolean;
}

export function CSVEditor({ initialCsvText, onChange, readOnly = false }: CSVEditorProps) {
  const { t } = useTranslation('common');
  const [data, setData] = useState<string[][]>([]);
  const [page, setPage] = useState(0);
  const pageSize = 100;

  useEffect(() => {
    // Parse initial CSV
    Papa.parse<string[]>(initialCsvText, {
      complete: (results) => {
        setData(results.data);
      },
      skipEmptyLines: true,
    });
  }, [initialCsvText]);

  const handleCellChange = (rowIndex: number, colIndex: number, value: string) => {
    if (readOnly || !onChange) return;
    const newData = [...data];
    if (!newData[rowIndex]) {
      newData[rowIndex] = [];
    }
    newData[rowIndex][colIndex] = value;
    setData(newData);
    
    // Unparse and trigger onChange
    const newCsvText = Papa.unparse(newData);
    onChange(newCsvText);
  };

  const totalPages = Math.ceil(data.length / pageSize);
  const paginatedData = useMemo(() => {
    return data.slice(page * pageSize, (page + 1) * pageSize);
  }, [data, page]);

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-color-muted-foreground">
        <p>{t('csv.empty')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-surface relative">
      <div className="flex items-center justify-end p-2 border-b border-border">
        <div className="flex items-center gap-2 text-style-body text-color-muted-foreground">
          <span>{t('csv.range', { start: page * pageSize + 1, end: Math.min((page + 1) * pageSize, data.length), total: data.length })}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded-surface p-1 hover:bg-muted disabled:opacity-50"
              aria-label={t('csv.previous')}
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded-surface p-1 hover:bg-muted disabled:opacity-50"
              aria-label={t('csv.next')}
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
      
      <div className="flex-1 overflow-auto">
        <table className="min-w-full divide-y divide-border border-collapse">
          <tbody className="divide-y divide-border bg-surface">
            {paginatedData.map((row, pRowIndex) => {
              const actualRowIndex = page * pageSize + pRowIndex;
              const isHeader = actualRowIndex === 0;
              return (
                <tr key={actualRowIndex} className={isHeader ? "bg-muted sticky top-0 z-10" : "hover:bg-muted"}>
                  <td className="w-12 px-2 py-1 text-style-caption text-color-muted-foreground bg-muted border-r border-b text-center sticky left-0 z-20">
                    {actualRowIndex + 1}
                  </td>
                  {row.map((cell, colIndex) => (
                    <td key={colIndex} className="border-r border-b border-border p-0 min-w-25">
                      <input
                        type="text"
                        value={cell || ''}
                        onChange={(e) => handleCellChange(actualRowIndex, colIndex, e.target.value)}
                        readOnly={readOnly}
                        className={`w-full px-3 py-2 text-style-body bg-transparent outline-none focus:ring-2 focus:ring-inset focus:ring-primary ${isHeader ? 'font-bold text-color-foreground' : 'text-color-foreground'}`}
                        placeholder={isHeader ? t('csv.column', { index: colIndex + 1 }) : ''}
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
