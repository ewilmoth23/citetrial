import { Link } from 'react-router-dom';
import { EmptyState } from '../components/ui';

export function NotFoundPage() {
  return (
    <EmptyState
      title="This trail ends here"
      description="The requested page or research record does not exist."
      action={
        <Link className="button-primary" to="/">
          Return to projects
        </Link>
      }
    />
  );
}
