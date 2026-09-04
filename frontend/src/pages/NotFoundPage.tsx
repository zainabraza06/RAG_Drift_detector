import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/states/EmptyState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export function NotFoundPage() {
  return (
    <Card className="mx-auto max-w-lg">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="That route does not exist in this application."
        action={
          <Link to="/">
            <Button variant="primary">Back to dashboard</Button>
          </Link>
        }
      />
    </Card>
  );
}
