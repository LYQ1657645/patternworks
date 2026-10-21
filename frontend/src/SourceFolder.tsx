import { useState } from "react";
import type { S3File } from "./api";
import Folder from "./vendor/react-bits/Folder";
import { useAppearance } from "./motion";

export default function SourceFolder({ files, selected, disabled, onSelect }: { files: S3File[]; selected: string; disabled: boolean; onSelect: (key: string) => void }) {
  const [open, setOpen] = useState(false);
  const { night, reduced } = useAppearance();
  const sample = files.slice(0, 3);
  return <div className="source-folder" aria-label="Source file folder">
    <Folder label="Source files" size={.95} color={night ? "#b39277" : "#7d9b7f"} paperColor="#fafbf4" theme={night ? "dark" : "light"}
      variant="solid" intro={false} peek={!reduced && !disabled} open={open && !disabled} onOpenChange={next => { if (!disabled) setOpen(next); }}
      tilt={reduced ? 0 : .25} bounce={reduced ? 0 : .15} speed={reduced ? 100 : 1.3} draggable={false} zoomOnClick={false} closeOnOutsideClick={false} layout="spread"
      onItemClick={(_, index) => { if (!disabled && sample[index]) onSelect(sample[index].key); }}
      items={sample.map(file => ({ title: file.key, content: <div className="source-paper"><span>{file.format.toUpperCase()}</span><strong>{file.key}</strong><small>{file.key === selected ? "Selected" : "Select file"}</small></div> }))} />
  </div>;
}
