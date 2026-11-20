import { Board, EventLog, Timeline } from '@/components/Board';
import { Chat } from '@/components/Chat';

export default function Overview() {
  return (
    <div className="page grid-2">
      <div className="stack"><Board /><Timeline compact /><EventLog /></div>
      <Chat />
    </div>
  );
}
