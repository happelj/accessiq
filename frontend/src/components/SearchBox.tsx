interface SearchBoxProps {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
}

export function SearchBox({ value, onChange, label, placeholder }: SearchBoxProps) {
  return (
    <label className="search-box">
      <span>{label}</span>
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
