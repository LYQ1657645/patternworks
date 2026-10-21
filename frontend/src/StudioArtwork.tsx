/** Decorative data-to-table illustration; never represents live application state. */
export default function StudioArtwork() {
  return <div className="studio-artwork" aria-hidden="true">
    <div className="art-orbit" />
    <span className="art-star">✳</span>
    <div className="art-note"><span className="art-tape" /><small>A LITTLE MESSY</small>
      <span className="art-scribble">names, dates,<br />a few loose ends.</span>
      <div className="art-lines"><i /><i /><i /></div>
    </div>
    <svg className="art-arrow" viewBox="0 0 120 80" fill="none"><path d="M8 15c40-25 85 7 52 31-24 18-3 35 45 15m-14-7 16 6-10 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    <div className="art-sheet"><div className="art-sheet-title"><span className="art-sheet-mark">✦</span> A clearer picture <span>↗</span></div>
      <div className="art-table"><i /><i /><i /><b /><b /><b /><b /><b /><b /><b /><b /><b /></div>
      <div className="art-sheet-footer"><span>●</span> Ready for what’s next.</div>
    </div>
    <span className="art-caption">a little order. a lot of possibility.</span>
  </div>;
}
