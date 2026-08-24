export interface SliderOption {
  label: string;
  value: number;
}

export interface SliderProps {
  options: SliderOption[];
  value: number;
  onChange: (value: number) => void;
  getColor?: (index: number, value: number) => string;
}

export function Slider({ options, value, onChange, getColor }: SliderProps) {
  const currentIndex = Math.max(0, options.findIndex(opt => opt.value === value));
  
  let sliderColor = 'bg-primary';
  if (getColor) {
    sliderColor = getColor(currentIndex, value);
  }

  return (
    <div className="relative pt-2 pb-8 select-none px-4">
      <div className="relative h-2 bg-muted rounded-full w-full">
        {/* Colored track */}
        <div 
          className={`absolute top-0 left-0 h-full rounded-full transition-all duration-300 ease-in-out ${sliderColor}`}
          style={{ width: `${(currentIndex / (options.length - 1)) * 100}%` }}
        />
        
        {/* Thumb */}
        <div 
          className={`absolute top-1/2 -translate-y-1/2 w-5 h-5 bg-surface border-4 rounded-full shadow transition-all duration-300 ease-in-out ${sliderColor.replace('bg-', 'border-')}`}
          style={{ left: `calc(${(currentIndex / (options.length - 1)) * 100}% - 10px)` }}
        />
        
        {/* Input Range */}
        <input 
          type="range" 
          min="0" 
          max={options.length - 1} 
          step="1"
          value={currentIndex}
          onChange={(e) => onChange(options[parseInt(e.target.value)].value)}
          className="absolute top-1/2 -translate-y-1/2 left-0 w-full h-8 opacity-0 cursor-pointer z-10 m-0"
        />
      </div>

      {/* Labels */}
      <div className="absolute left-4 right-4 mt-4 h-4">
        {options.map((opt, i) => (
          <div 
            key={opt.value}
            className={`absolute top-0 -translate-x-1/2 text-style-caption-strong cursor-pointer transition-colors ${
              i === currentIndex ? 'text-color-foreground font-bold' : 'text-color-muted-foreground hover:text-color-foreground'
            }`}
            style={{ left: `${(i / (options.length - 1)) * 100}%` }}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </div>
        ))}
      </div>
    </div>
  );
}
