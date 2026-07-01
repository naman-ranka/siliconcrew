import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, params.path);
}

async function handleProxy(request: NextRequest, pathSegments: string[]) {
  // Read backend URL at runtime (server-side, so environment variables are fully dynamic)
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const path = pathSegments.join("/");
  const url = new URL(request.url);
  const searchParams = url.search;
  
  const targetUrl = `${backendUrl}/api/${path}${searchParams}`;
  
  // Forward incoming headers (except host/connection to avoid routing conflicts)
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host" && key.toLowerCase() !== "connection") {
      headers.set(key, value);
    }
  });

  const body = ["GET", "HEAD", "OPTIONS"].includes(request.method) ? undefined : await request.blob();

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers: headers,
      body: body,
      cache: "no-store",
    });

    const responseBody = await response.blob();
    
    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      responseHeaders.set(key, value);
    });

    return new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error: any) {
    console.error("Next.js proxy error:", error);
    return NextResponse.json(
      { detail: `Failed to proxy request to backend: ${error.message}` },
      { status: 502 }
    );
  }
}
