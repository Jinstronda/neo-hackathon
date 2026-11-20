import { Board, EventLog } from '@/components/Board';
import { Chat } from '@/components/Chat';
import { Graph } from '@/components/Graph';

export default function Overview() {
  return (
    <div className="page ov">
      <h1 className="sr-only">Overview</h1>
      <div className="ov-main">
        <Graph />
        <div className="ov-low"><Board compact /><EventLog /></div>
      </div>
      <Chat />
    </div>
  );
}
