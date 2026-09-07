import cv2
import numpy as np

class StitchingError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(self.message)

class InsufficientOverlap(StitchingError):
    def __init__(self, message="Not enough matching features were found between your images."):
        super().__init__("INSUFFICIENT_OVERLAP", message)

class ProcessingError(StitchingError):
    def __init__(self, message="An error occurred while processing the panorama."):
        super().__init__("PROCESSING_ERROR", message)

def load_and_preprocess(image_bytes, max_dim=3000):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ProcessingError("One of your images couldn't be read. Try a different file.")
    
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img, gray

def detect_and_match(gray1, gray2):
    sift = cv2.SIFT_create()
    kp1, des1 = sift.detectAndCompute(gray1, None)
    kp2, des2 = sift.detectAndCompute(gray2, None)
    
    if des1 is None or des2 is None:
        raise InsufficientOverlap("Failed to extract features from images.")

    matcher = cv2.BFMatcher()
    matches = matcher.knnMatch(des1, des2, k=2)
    
    good = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good.append(m)
            
    if len(good) < 10:
        raise InsufficientOverlap()
        
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    
    return src_pts, dst_pts

def warp_and_blend(img1, img2, H):
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    
    pts1 = np.float32([[0, 0], [0, h1], [w1, h1], [w1, 0]]).reshape(-1, 1, 2)
    pts2 = np.float32([[0, 0], [0, h2], [w2, h2], [w2, 0]]).reshape(-1, 1, 2)
    
    pts2_transformed = cv2.perspectiveTransform(pts2, H)
    pts = np.concatenate((pts1, pts2_transformed), axis=0)
    
    [xmin, ymin] = np.int32(pts.min(axis=0).ravel() - 0.5)
    [xmax, ymax] = np.int32(pts.max(axis=0).ravel() + 0.5)
    
    t = [-xmin, -ymin]
    Ht = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]])
    
    out_w, out_h = xmax - xmin, ymax - ymin
    
    # Check if the canvas size is reasonable (avoid memory errors)
    if out_w > 15000 or out_h > 15000:
         raise ProcessingError("Images are too different in perspective to stitch reliably.")
         
    # Warp img2
    warped_img2 = cv2.warpPerspective(img2, Ht.dot(H), (out_w, out_h))
    
    # Place img1 in the new canvas
    warped_img1 = np.zeros_like(warped_img2, dtype=np.uint8)
    y_start, y_end = t[1], h1+t[1]
    x_start, x_end = t[0], w1+t[0]
    warped_img1[y_start:y_end, x_start:x_end] = img1
    
    # Create geometric masks for both images
    mask1 = np.zeros((out_h, out_w), dtype=np.uint8)
    mask1[y_start:y_end, x_start:x_end] = 255
    
    img2_mask_orig = np.ones((h2, w2), dtype=np.uint8) * 255
    mask2 = cv2.warpPerspective(img2_mask_orig, Ht.dot(H), (out_w, out_h))
    
    # Compute distance transforms for feathering (alpha blending)
    dist1 = cv2.distanceTransform(mask1, cv2.DIST_L2, 3)
    dist2 = cv2.distanceTransform(mask2, cv2.DIST_L2, 3)
    
    # Calculate alpha weight based on distance to the closest boundary
    alpha = dist1 / (dist1 + dist2 + 1e-8)
    alpha = cv2.merge([alpha, alpha, alpha])
    
    # Blend the images using the alpha weight
    final = (warped_img1 * alpha + warped_img2 * (1.0 - alpha)).astype(np.uint8)
    
    return final

def crop_black_padding(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img
    
    # Get bounding box of all non-black regions
    x, y, w, h = cv2.boundingRect(np.vstack(contours))
    return img[y:y+h, x:x+w]

def stitch_images(image_bytes_list, output_format='jpg'):
    if len(image_bytes_list) < 2 or len(image_bytes_list) > 3:
        raise ProcessingError("Exactly 2 or 3 images required.")
        
    base_img, base_gray = load_and_preprocess(image_bytes_list[0])
    
    for i in range(1, len(image_bytes_list)):
        curr_img, curr_gray = load_and_preprocess(image_bytes_list[i])
        
        src_pts, dst_pts = detect_and_match(curr_gray, base_gray)
        
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if H is None:
            raise InsufficientOverlap()
            
        inliers = mask.sum()
        if inliers / len(mask) < 0.2 or inliers < 10:
            raise InsufficientOverlap("Not enough confident matching features. Please try images with more overlap.")
            
        base_img = warp_and_blend(base_img, curr_img, H)
        base_gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        
    # Crop out pure black padding
    base_img = crop_black_padding(base_img)
    
    ext = f'.{output_format}'
    success, encoded_img = cv2.imencode(ext, base_img)
    if not success:
        raise ProcessingError("Failed to encode stitched image.")
        
    return encoded_img.tobytes()
