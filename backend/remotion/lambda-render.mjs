// Dispatch a render to Remotion on AWS Lambda, wait for it, download the result.
// Called by app/services/render_lambda.py on the render worker.
//   argv: propsFile outPath functionName region serveUrl
// AWS credentials come from the standard AWS_* env vars.
import fs from 'node:fs';
import {renderMediaOnLambda, getRenderProgress, downloadMedia} from '@remotion/lambda';

const [, , propsFile, outPath, functionName, region, serveUrl] = process.argv;

if (!propsFile || !outPath || !functionName || !region || !serveUrl) {
  process.stderr.write('usage: lambda-render.mjs <props> <out> <fn> <region> <serveUrl>\n');
  process.exit(2);
}

const inputProps = JSON.parse(fs.readFileSync(propsFile, 'utf-8'));

const {renderId, bucketName} = await renderMediaOnLambda({
  region,
  functionName,
  serveUrl,
  composition: 'Story',
  inputProps,
  codec: 'h264',
  imageFormat: 'jpeg',
  privacy: 'private',
});
process.stderr.write(`renderId=${renderId}\n`);

// poll until done
for (;;) {
  const p = await getRenderProgress({renderId, bucketName, functionName, region});
  if (p.fatalErrorEncountered) {
    process.stderr.write('fatal: ' + JSON.stringify(p.errors?.slice?.(0, 2) || p.errors) + '\n');
    process.exit(1);
  }
  if (p.done) {
    process.stderr.write(`done (${Math.round((p.timeToFinish || 0) / 1000)}s, $${(p.costs?.accruedSoFar ?? 0).toFixed(4)})\n`);
    break;
  }
  process.stderr.write(`progress ${(p.overallProgress * 100).toFixed(0)}%\n`);
  await new Promise((r) => setTimeout(r, 2000));
}

await downloadMedia({region, bucketName, renderId, outPath});
process.stderr.write('downloaded\n');
